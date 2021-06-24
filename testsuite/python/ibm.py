#
# Copyright (C) 2013-2019 The ESPResSo project
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
import numpy as np
import itertools
import unittest as ut

import espressomd
import espressomd.interactions
try:
    from espressomd.virtual_sites import VirtualSitesInertialessTracers
except ImportError:
    pass


class IBM(ut.TestCase):
    '''Test IBM implementation with a Langevin thermostat.'''
    system = espressomd.System(box_l=3 * [10.])
    system.time_step = 0.05
    system.cell_system.skin = 0.1

    def tearDown(self):
        self.system.part.clear()
        self.system.thermostat.turn_off()

    def compute_dihedral_angle(self, pos0, pos1, pos2, pos3):
        # first normal vector
        n1 = np.cross((pos1 - pos0), (pos2 - pos0))
        n2 = np.cross((pos2 - pos0), (pos3 - pos0))

        norm1 = np.linalg.norm(n1)
        norm2 = np.linalg.norm(n2)
        n1 = n1 / norm1
        n2 = n2 / norm2

        cos_alpha = min(1, np.dot(n1, n2))
        alpha = np.arccos(cos_alpha)
        return alpha

    def test_tribend(self):
        # two triangles with bending interaction
        # move nodes, should relax back

        system = self.system
        system.virtual_sites = VirtualSitesInertialessTracers()
        system.thermostat.set_langevin(kT=0, gamma=10, seed=1)

        # Add four particles
        p0 = system.part.add(pos=[5, 5, 5])
        p1 = system.part.add(pos=[5, 5, 6])
        p2 = system.part.add(pos=[5, 6, 6])
        p3 = system.part.add(pos=[5, 6, 5])

        # Add first triel, weak modulus
        tri1 = espressomd.interactions.IBM_Triel(
            ind1=p0.id, ind2=p1.id, ind3=p2.id, elasticLaw="Skalak", k1=0.1, k2=0, maxDist=2.4)
        system.bonded_inter.add(tri1)
        p0.add_bond((tri1, p1, p2))

        # Add second triel, strong modulus
        tri2 = espressomd.interactions.IBM_Triel(
            ind1=p0.id, ind2=p2.id, ind3=p3.id, elasticLaw="Skalak", k1=10, k2=0, maxDist=2.4)
        system.bonded_inter.add(tri2)
        p0.add_bond((tri2, p2, p3))

        # Add bending
        tribend = espressomd.interactions.IBM_Tribend(
            ind1=p0.id, ind2=p1.id, ind3=p2.id, ind4=p3.id, kb=1, refShape="Initial")
        system.bonded_inter.add(tribend)
        p0.add_bond((tribend, p1, p2, p3))

        # twist
        system.part[:].pos = system.part[:].pos + np.random.random((4, 3))

        # Perform integration
        system.integrator.run(200)
        angle = self.compute_dihedral_angle(p0.pos, p1.pos, p2.pos, p3.pos)
        self.assertLess(angle, 2E-2)

        # IBM doesn't implement energy and pressure kernels.
        energy = self.system.analysis.energy()
        pressure = self.system.analysis.pressure()
        self.assertAlmostEqual(energy['bonded'], 0., delta=1e-10)
        self.assertAlmostEqual(pressure['bonded'], 0., delta=1e-10)

    def test_triel(self):
        system = self.system
        system.virtual_sites = VirtualSitesInertialessTracers()
        system.thermostat.set_langevin(kT=0, gamma=1, seed=1)

        # Add particles: 0-2 are not bonded, 3-5 are bonded
        non_bound = system.part.add(pos=[[5, 5, 5], [5, 5, 6], [5, 6, 6]])

        p3 = system.part.add(pos=[2, 5, 5])
        p4 = system.part.add(pos=[2, 5, 6])
        p5 = system.part.add(pos=[2, 6, 6])

        # Add triel for 3-5
        tri = espressomd.interactions.IBM_Triel(
            ind1=p3.id, ind2=p4.id, ind3=p5.id, elasticLaw="Skalak", k1=15,
            k2=0, maxDist=2.4)
        system.bonded_inter.add(tri)
        p3.add_bond((tri, p4, p5))

        system.part[:].pos = system.part[:].pos + np.array((
            (0, 0, 0), (1, -.2, .3), (1, 1, 1),
            (0, 0, 0), (1, -.2, .3), (1, 1, 1)))

        distorted_pos = np.copy(non_bound.pos)

        system.integrator.run(110)
        dist1bound = system.distance(p3, p4)
        dist2bound = system.distance(p3, p5)

        # check bonded particles. Distance should restore to initial config
        self.assertAlmostEqual(dist1bound, 1, delta=0.05)
        self.assertAlmostEqual(dist2bound, np.sqrt(2), delta=0.05)

        # check not bonded particles. Positions should still be distorted
        np.testing.assert_allclose(np.copy(non_bound.pos), distorted_pos)

    def test_volcons(self):
        '''Check volume conservation forces on a simple mesh (cube).'''
        system = self.system
        system.virtual_sites = VirtualSitesInertialessTracers()
        system.thermostat.set_langevin(kT=0, gamma=1, seed=1)

        # Place particles on a cube.
        positions = list(itertools.product((0, 1), repeat=3))
        positions = positions[:4] + positions[6:] + positions[4:6]
        positions = np.array(positions) - 0.5
        system.part.add(pos=positions + system.box_l / 2., virtual=8 * [True])

        # Divide the cube. All triangle normals must point inside the mesh.
        # Use the right hand rule to determine the order of the indices.
        triangles = [(0, 1, 2), (1, 3, 2),
                     (2, 3, 4), (3, 5, 4),
                     (4, 5, 6), (5, 7, 6),
                     (6, 7, 0), (7, 1, 0),
                     (0, 2, 4), (0, 4, 6),
                     (1, 5, 3), (1, 7, 5)]
        # Add triangle bonds that don't contribute to the force (infinite
        # elasticity). These bonds are needed to calculate the mesh volume.
        for id1, id2, id3 in triangles:
            bond = espressomd.interactions.IBM_Triel(
                ind1=id3, ind2=id2, ind3=id1, elasticLaw="Skalak", k1=0., k2=0., maxDist=3)
            system.bonded_inter.add(bond)
            system.part[id1].add_bond((bond, id2, id3))

        # Add volume conservation force.
        volCons = espressomd.interactions.IBM_VolCons(softID=15, kappaV=1.)
        system.bonded_inter.add(volCons)
        for p in system.part:
            p.add_bond((volCons,))

        # Run the integrator to initialize the mesh reference volume.
        system.integrator.run(0, recalc_forces=True)

        # The restorative force is zero at the moment.
        np.testing.assert_almost_equal(np.copy(self.system.part[:].f), 0.)

        # Double the cube dimensions. The volume increases by a factor of 8.
        system.part[:].pos = 2. * positions + system.box_l / 2.
        system.integrator.run(0, recalc_forces=True)
        ref_forces = 1.75 * np.array(
            [(1, 2, 2), (2, 1, -2), (2, -1, 1), (1, -2, -1),
             (-1, -2, 2), (-2, -1, -2), (-2, 1, 1), (-1, 2, -1)])
        np.testing.assert_almost_equal(
            np.copy(self.system.part[:].f), ref_forces)

        # IBM doesn't implement energy and pressure kernels.
        energy = self.system.analysis.energy()
        pressure = self.system.analysis.pressure()
        self.assertAlmostEqual(energy['bonded'], 0., delta=1e-10)
        self.assertAlmostEqual(pressure['bonded'], 0., delta=1e-10)


if __name__ == "__main__":
    ut.main()
