/*
 * Copyright (C) 2010-2022 The ESPResSo project
 *
 * This file is part of ESPResSo.
 *
 * ESPResSo is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * ESPResSo is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
#ifndef CORE_GRID_BASED_ALGORITHMS_FD_ELECTROSTATICS_HPP
#define CORE_GRID_BASED_ALGORITHMS_FD_ELECTROSTATICS_HPP

#include <cufft.h>

class FdElectrostatics {
public:
  struct InputParameters {
    float prefactor;
    int dim_x, dim_y, dim_z;
    float agrid;
  };

  struct Parameters : public InputParameters {
    Parameters() = default;
    Parameters(InputParameters &inputParameters)
        : InputParameters(inputParameters) {
      charge_potential = nullptr;
      greensfcn = nullptr;
      dim_x_padded = (inputParameters.dim_x / 2 + 1) * 2;
    }

    cufftComplex *charge_potential;
    cufftReal *greensfcn;
    int dim_x_padded;
  };

  struct Grid {
    float *grid;
    int dim_x;
    int dim_y;
    int dim_z;
    float agrid;
  };

  ~FdElectrostatics();
  FdElectrostatics(InputParameters inputParameters, cudaStream_t stream);
  void calculatePotential();
  void calculatePotential(cufftComplex *charge_potential);
  Grid getGrid();

private:
  Parameters parameters;
  cudaStream_t cuda_stream;
  cufftHandle plan_fft;
  cufftHandle plan_ifft;
  bool initialized;
};

#endif
