import jax.numpy as jnp
import matplotlib.pyplot as plt
import optax
from diffmpm.element import Linear1D
from diffmpm.material import SimpleMaterial
from diffmpm.mesh import _MeshBase
from diffmpm.particle import Particles
from diffmpm.solver import MPMExplicit
from jax import value_and_grad, grad, jit
from tqdm import tqdm

E_true = 100
material = SimpleMaterial({"E": E_true, "density": 1})
elements = Linear1D(1, 1, jnp.array([0]))
particles = Particles(
    jnp.array([0.5]).reshape(1, 1, 1), material, jnp.array([0])
)
particles.initialize()
b1 = jnp.pi * 0.5
particles.velocity += 0.1
particles.set_mass_volume(1.0)
dt = 0.001
nsteps = 2000
mesh = _MeshBase({"particles": [particles], "elements": elements})

mpm = MPMExplicit(mesh, dt, scheme="usl")
true_result = mpm.solve_jit(nsteps, 0)
target_vel = true_result["velocity"]

from jax import debug


@jit
def compute_loss(E, mpm, target_vel):
    # debug.breakpoint()
    mpm.mesh.particles[0].material.properties["E"] = E
    mpm.mesh.particles[0].velocity = mesh.particles[0].velocity.at[:].set(0.1)
    # debug.breakpoint()
    nsteps = 2000
    result = mpm.solve_jit(nsteps, 0)
    vel = result["velocity"]
    loss = jnp.linalg.norm(vel - target_vel)
    return loss


def optax_adam(params, niter, mpm, target_vel):
    # Initialize parameters of the model + optimizer.
    start_learning_rate = 1e-1
    optimizer = optax.adam(start_learning_rate)
    opt_state = optimizer.init(params)

    param_list = []
    loss_list = []
    # A simple update loop.
    t = tqdm(range(niter), desc=f"E: {params}")
    for _ in t:
        lo, grads = value_and_grad(compute_loss)(params, mpm, target_vel)
        updates, opt_state = optimizer.update(grads, opt_state)
        params = optax.apply_updates(params, updates)
        t.set_description(f"E: {params}")
        param_list.append(params)
        loss_list.append(lo)
    return param_list, loss_list


params = 95.0
material = SimpleMaterial({"E": params, "density": 1})
elements = Linear1D(1, 1, jnp.array([0]))
particles = Particles(
    jnp.array([0.5]).reshape(1, 1, 1), material, jnp.array([0])
)
particles.velocity += 0.1
particles.set_mass_volume(1.0)
mesh = _MeshBase({"particles": [particles], "elements": elements})

mpm = MPMExplicit(mesh, dt, scheme="usl")
param_list, loss_list = optax_adam(
    params, 400, mpm, target_vel
)  # ADAM optimizer
# print("E: {}".format(result))

fig, ax = plt.subplots(1, 2, figsize=(16, 6))
ax[0].plot(param_list, "ko", markersize=2, label="E")
ax[0].grid()
ax[0].legend()
ax[1].plot(loss_list, "ko", markersize=2, label="Loss")
ax[1].grid()
ax[1].legend()
plt.show()
