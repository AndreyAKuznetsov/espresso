#
# Copyright (C) 2013-2022 The ESPResSo project
#
# This file is part of ESPResSo.
#
# ESPResSo is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ESPResSo is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Perform a grand canonical simulation of a system in contact
with a salt reservoir while maintaining a constant chemical potential.
"""
epilog = """
Takes two command line arguments as input: 1) the reservoir salt
concentration in units of 1/sigma^3 and 2) the excess chemical
potential of the reservoir in units of kT.

The excess chemical potential of the reservoir needs to be determined
prior to running the grand canonical simulation using the script called
widom_insertion.py which simulates a part of the reservoir at the
prescribed salt concentration. Be aware that the reservoir excess
chemical potential depends on all interactions in the reservoir system.
"""
import numpy as np
import argparse

import espressomd
import espressomd.reaction_methods
import espressomd.electrostatics

required_features = ["P3M", "WCA"]
espressomd.assert_features(required_features)

parser = argparse.ArgumentParser(epilog=__doc__ + epilog)
parser.add_argument('cs_bulk', type=float,
                    help="bulk salt concentration [1/sigma^3], e.g. 1e-3")
parser.add_argument('excess_chemical_potential', type=float,
                    help="excess chemical potential [kT] (obtained from "
                         "Widom's insertion method), e.g. -0.36")
args = parser.parse_args()

# System parameters
#############################################################

cs_bulk = args.cs_bulk
excess_chemical_potential_pair = args.excess_chemical_potential
box_l = 50.0

# Integration parameters
#############################################################
system = espressomd.System(box_l=[box_l, box_l, box_l])
np.random.seed(seed=42)

system.time_step = 0.01
system.cell_system.skin = 0.4
temperature = 1.0


#############################################################
#  Setup System                                             #
#############################################################

# Particle setup
#############################################################
# type 0 = HA
# type 1 = A-
# type 2 = H+

for i in range(int(cs_bulk * box_l**3)):
    system.part.add(pos=np.random.random(3) * system.box_l, type=1, q=-1)
    system.part.add(pos=np.random.random(3) * system.box_l, type=2, q=1)

wca_eps = 1.0
wca_sig = 1.0
types = [0, 1, 2]
for type_1 in types:
    for type_2 in types:
        system.non_bonded_inter[type_1, type_2].wca.set_params(
            epsilon=wca_eps, sigma=wca_sig)

RE = espressomd.reaction_methods.ReactionEnsemble(
    kT=temperature, exclusion_range=wca_sig, seed=3)
RE.add_reaction(
    gamma=cs_bulk**2 * np.exp(excess_chemical_potential_pair / temperature),
    reactant_types=[], reactant_coefficients=[], product_types=[1, 2],
    product_coefficients=[1, 1], default_charges={1: -1, 2: +1})
print(RE.get_status())
system.setup_type_map(type_list=[0, 1, 2])

# Set the hidden particle type to the lowest possible number to speed
# up the simulation
RE.set_non_interacting_type(type=max(types) + 1)

RE.reaction(steps=10000)

p3m = espressomd.electrostatics.P3M(prefactor=2.0, accuracy=1e-3)
system.actors.add(p3m)
p3m_params = p3m.get_params()
for key, value in p3m_params.items():
    print(f"{key} = {value}")


# Warmup
#############################################################
# warmup integration (steepest descent)
warm_steps = 20
warm_n_times = 20
min_dist = 0.9 * wca_sig

# minimize energy using min_dist as the convergence criterion
system.integrator.set_steepest_descent(f_max=0, gamma=1e-3,
                                       max_displacement=0.01)
i = 0
while system.analysis.min_dist() < min_dist and i < warm_n_times:
    print(f"minimization: {system.analysis.energy()['total']:+.2e}")
    system.integrator.run(warm_steps)
    i += 1

print(f"minimization: {system.analysis.energy()['total']:+.2e}")
print()
system.integrator.set_vv()

# activate thermostat
system.thermostat.set_langevin(kT=temperature, gamma=.5, seed=42)

# MC warmup
RE.reaction(steps=1000)

n_int_cycles = 10000
n_int_steps = 600
num_As = []
deviation = None
for i in range(n_int_cycles):
    RE.reaction(steps=10)
    system.integrator.run(steps=n_int_steps)
    num_As.append(system.number_of_particles(type=1))
    if i > 2 and i % 50 == 0:
        print(f"HA {system.number_of_particles(type=0)}",
              f"A- {system.number_of_particles(type=1)}",
              f"H+ {system.number_of_particles(type=2)}")
        concentration_in_box = np.mean(num_As) / box_l**3
        deviation = (concentration_in_box - cs_bulk) / cs_bulk * 100
        n_A_mean = np.mean(num_As)
        n_A_stde = 1.96 * np.std(num_As, ddof=1) / len(num_As)
        print(f"average num A {n_A_mean:.1f} +/- {n_A_stde:.1f}, "
              f"average concentration {concentration_in_box:.8f}, "
              f"deviation to target concentration {deviation:.2f}%")
