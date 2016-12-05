#include "observables.hpp"

namespace Observables {
std::vector<std::shared_ptr<Observables::Observable>> auto_update_observables;

void auto_update() {
  for (auto& o : auto_update_observables) {
    o->calculate();
  }
}


}

