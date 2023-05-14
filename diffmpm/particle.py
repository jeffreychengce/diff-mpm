from typing import Callable

import jax.numpy as jnp
from jax import jit, vmap
from jax.tree_util import register_pytree_node_class

from diffmpm.element import _Element
from diffmpm.material import Material


# @register_pytree_node_class
class Particles:
    def __init__(
        self,
        loc: jnp.ndarray,
        material: Material,
        element_ids: jnp.ndarray,
        shapefn: Callable,
    ):
        """
        Initialise a container of particles.

        Arguments
        ---------
        loc: jax.numpy.ndarray
            Location of the particles. Expected shape (nparticles, 1, ndim)
        material: diffmpm.material.Material
            Type of material for the set of particles.
        element_ids: jax.numpy.ndarray
            The element ids that the particles belong to. This contains
        information that will make sense only with the information of
        the mesh that is being considered.
        TODO: Check if it is feasible to move this to Element/Mesh.
        shapefn: Callable
            Shape function used by the elements that the particles are in.
        """
        self.material: Material = material
        self.element_ids: jnp.ndarray = element_ids
        if len(loc.shape) != 3:
            raise ValueError(
                f"`loc` should be of size (nparticles, ndim); found {loc.shape}"
            )
        self.loc: jnp.ndarray = loc
        self.initialize(shapefn)

    def initialize(self, shapefn: Callable):
        """
        Initialize the particle properties.

        Arguments
        ---------
        shapefn: Callable
            A function used by the mesh elements to map the particles to
        their reference coordinates (xi).
        """
        self.mass = jnp.zeros((self.loc.shape[0], 1, 1))
        self.density = jnp.zeros_like(self.mass)
        self.volume = jnp.zeros_like(self.mass)
        self.velocity = jnp.zeros_like(self.loc)
        self.acceleration = jnp.zeros_like(self.loc)
        self.momentum = jnp.zeros_like(self.loc)
        self.stress = jnp.zeros_like(self.loc)
        self.strain = jnp.zeros_like(self.loc)
        self.strain_rate = jnp.zeros_like(self.loc)
        self.dstrain = jnp.zeros_like(self.loc)
        self.f_ext = jnp.zeros_like(self.loc)
        self.reference_loc = jnp.zeros_like(self.loc)

    def __len__(self):
        """Set length of the class as number of particles."""
        return self.loc.shape[0]

    def __repr__(self):
        """Informative repr showing number of particles."""
        return f"Particles(nparticles={len(self)})"

    def set_mass(self, m):
        """
        Set particle mass.

        Arguments
        ---------
        m: float, array_like
            Mass to be set for particles. If scalar, mass for all
        particles is set to this value.
        """
        if jnp.isscalar(m):
            self.mass = jnp.ones_like(self.loc) * m
        elif m.shape == self.mass.shape:
            self.mass = m
        else:
            raise ValueError(
                f"Incompatible shapes. Expected {self.mass.shape}, "
                f"found {m.shape}."
            )

    def set_particle_element_ids(self, elements: _Element):
        """
        Set the element IDs for the particles.

        If the particle doesn't lie between the boundaries of any
        element, it sets the element index to -1.
        """

        @jit
        def f(x):
            idl = (
                len(elements.nodes.loc)
                - 1
                - jnp.asarray(elements.nodes.loc[::-1] <= x).nonzero(
                    size=1, fill_value=-1
                )[0][-1]
            )
            idg = (
                jnp.asarray(elements.nodes.loc > x).nonzero(
                    size=1, fill_value=-1
                )[0][0]
                - 1
            )
            return (idl, idg)

        ids = vmap(f)(self.loc)
        self.element_ids = jnp.where(
            ids[0] == ids[1], ids[0], jnp.ones_like(ids[0]) * -1
        )

    def update_velocity(self, elements: _Element, dt: float):
        """
        Transfer nodal velocity to particles.

        The velocity is calculated based on the total force at nodes.

        Arguments
        ---------
        elements: diffmpm.element._Element
            Elements whose nodes are used to transfer the velocity.
        dt : float
            Timestep.
        """
        mapped_positions = elements.shapefn(self.reference_loc)
        mapped_ids = vmap(elements.id_to_node_ids)(self.element_ids).squeeze()
        total_force = elements.nodes.get_total_force()
        self.velocity = self.velocity.at[:].add(
            jnp.sum(
                mapped_positions
                * jnp.divide(
                    total_force[mapped_ids], elements.nodes.mass[mapped_ids]
                )
                * dt,
                axis=1,
            )
        )

    def compute_gradient_velocity(self, elements: _Element):
        mapped_coords = elements.id_to_node_loc(self.element_ids).squeeze(-1)
        dn_dx_ = vmap(elements.shapefn_grad)(
            self.reference_loc[:, jnp.newaxis, ...], mapped_coords
        )
        mapped_vel = vmap(elements.id_to_node_vel)(self.element_ids)
        # TODO: This will need to change to be more general for ndim.
        L = jnp.einsum("ijk, ikj -> ijk", dn_dx_, mapped_vel).sum(axis=2)
        return L
