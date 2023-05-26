# %%
import numpy as np

from sphpc import *

# np.random.seed(42)
EXPERIMENET_ID = "3D"
DATAFOLDER = "./data/" + EXPERIMENET_ID +"/"
# make_dir(DATAFOLDER)

#params:

IC = "Vrandn"         ## TODO Change this and add proper Taylor-Green IC
# method = "AV_neg_rel" 

T = 400
t_save = 1   #initial time for saving
vmag = 1.0   #initial magnitude of Taylor-Green velocity

c = 0.9157061661168617
h = 0.2
α = 0.45216843078299573
β = 0.3346233846532608
γ = 1                     ## TODO Equal 7 in the paper (see fig 1)
θ = 0.00430899795067121
dt = 0.4 * h / c

pi = np.pi
D_LIM = 2*pi    ## domain limit accors all axis

D = 3
halfres = 15; #produces grid of 2^halfres x 2^halfres x 2^halfres number of particles

cube = CubeGeom(x_lim=D_LIM, y_lim=D_LIM, z_lim=D_LIM, halfres=halfres)

N = cube.meshgrid.shape[0]
m = (D_LIM)**D / N       ## constant mass of each particle

## Not the same sigma as in the paper (see eq.14 Woodward 2023)
# sigma = (10. / (7. * pi * h * h)); #2D normalizing factor
sigma = 1/(pi*h**3)  #3D normalizing factor


# %%

def W(r, h):
  q = r / h   
  if (q > 2.):
    return 0
  if (q > 1.):
    return (sigma * (2. - q)**3 / 4.)
  return (sigma * (1. - 1.5 * q * q * (1. - q / 2.)))   ## ERROR in

# H(r) = (d W / d r) / r
# Remember: dW(r)/dr = r \times H(r) is a vector
def H(r, h):
  q = r / h
  if (q > 2.):
    return 0
  if (q > 1.):
    return (-3. * sigma * (2. - q)**2 / (4. * h * r))
  return (sigma * (-3. + 9. * q / 4.) / (h * h))  ## TODO ERROR divide by h*r, not h*h


## Equation of state
def P(rho):
  return (c**2 * (rho**γ - 1.) / γ)


## Speed of sound of particle rho
def compute_c(rho, c, γ):
  return c * rho**(0.5*(γ - 1))

## Artificial viscosity
def compute_Π(Xij, Vij, ρi, ρj, α, β, h, c):
  c_bar = (compute_c(ρi, c, γ) + compute_c(ρj, c, γ)) / 2.
  ρ_bar = (ρi + ρj) / 2.

  if (Xij.T@Vij < 0.):
    μ = h * (Xij.T@Vij) / (Xij.T@Xij + 0.01*(h**2))
    Π = (-α*c_bar*μ + β*(μ**2)) / ρ_bar
  else:
    Π = 0.

  return Π

## Density
def compute_densities(neighbor_ids, distances, h):
  N = len(neighbor_ids)
  ρ = np.zeros((N,))

  for i in range(N):
      ρ[i] += m * W(0., h)     ## i is its own neighbor
      for j_, j in enumerate(neighbor_ids[i]):
          ρ[i] += m * W(distances[i][j_], h)

  return ρ


## Acceleration force
def compute_acc_forces(X, V, ρ, neighbor_ids, distances, α, β, h, c):

  N = len(neighbor_ids)

  # Drop the element itself (if using KDTree)
  # neighbor_ids = [ np.delete(x, 0) for x in neighbor_ids]
  # distances = [ np.delete(x, 0) for x in distances]

  F = np.zeros_like(X)

  for i in range(N):
    vali = P(ρ[i]) / (ρ[i]**2)

    for j_, j in enumerate(neighbor_ids[i]):

      ## Compute artificial viscosity
      Xij = X[i] - X[j]
      Vij = V[i] - V[j]
      for d in range(D):
        while (Xij[d] > D_LIM/2.): Xij[d] -= D_LIM
        while (Xij[d] < -D_LIM/2.): Xij[d] += D_LIM
      Πij = compute_Π(Xij, Vij, ρ[i], ρ[j], α, β, h, c)

      # Πij = 0.    ## TODO Delete US
      # Xij = 0.

      ## Add up all forces
      valj = P(ρ[j]) / (ρ[j]**2)

      # vali, valj = 1e-2, 1e-2   ## TODO Delete US

      F[i] += -m*(vali + valj + Πij) * H(distances[i][j_], h) * Xij ## No external forces for now TODO Add later

      # F[i] = np.maximum(np.minimum(F[i], 1*np.ones(3)), -1*np.ones(3))   ## TODO Remove this line

  ke = 0.5 * np.mean(ρ * np.sum(V**2, axis=-1))

  # F += θ * V / ke
  F += θ * (V - np.mean(V, axis=0)) / (2*ke)    ## TODO Change to the above as in the paper

  return F


## %%

## Algorithm begins here

print("**************** Simulating the particle flow ***************")

X = cube.meshgrid + 0.0005 * (np.random.uniform(0., 1., size=cube.meshgrid.shape) - 0.5)
X = np.mod(X, D_LIM)

V = vmag * np.random.normal(0., 1., size=X.shape)

trajs, vels = np.zeros((T+1, N, D)), np.zeros((T+1, N, D))


trajs[0:, :, :] = X
vels[0:, :, :] = V

rhos = np.zeros((T+1, N))
# neighbor_ids, distances = find_neighbours(X, X, h)
neighbor_ids, distances = periodic_fixed_radius_nearest_neighbor(X, D_LIM, h)
ρ = compute_densities(neighbor_ids, distances, h)
rhos[0, :] = ρ


for t in range(1, T+1):

  ## TODO Find neighbours in a periodic way: hash table
  # neighbor_ids, distances = find_neighbours(X, X, h)
  neighbor_ids, distances = periodic_fixed_radius_nearest_neighbor(X, D_LIM, h)

  ρ = compute_densities(neighbor_ids, distances, h)
  F = compute_acc_forces(X, V, ρ, neighbor_ids, distances, α, β, h, c)

  Vbef = np.copy(V)

  ## Verlet advection scheme part 1
  X, V = half_verlet_scheme(X, V, F, dt)
  X = np.mod(X, D_LIM)

  if (np.isnan(X).any()):
    print("XXXXXXXXXXXXXXX \n\n\n")
    print(X[np.isnan(X[:,0])])
    nanpos = np.argwhere(np.isnan(X))
    print(nanpos)

    print("vbef\n", Vbef[nanpos[:, 0][::3]])
    print("vels\n", V[nanpos[:, 0][::3]])
    print("force\n", F[nanpos[:, 0][::3]])

    print("rho", ρ[ρ<0])
    print("forever dt", dt)
    break


  if (np.isnan(V).any() or np.isinf(V).any()):
    print("VVVVVVVVVVVV \n\n\n")

    print(V[np.isinf(V[:,0])])
    nanpos = np.argwhere(np.isinf(V))
    print(nanpos)

    print("X\n", X[nanpos[:, 0][::3]])
    print("vels\n", V[nanpos[:, 0][::3]])
    print("force\n", F[nanpos[:, 0][::3]])

    print("rho", ρ[ρ<0])
    print("forever dt", dt)

    break


  ρ = compute_densities(neighbor_ids, distances, h)
  F = compute_acc_forces(X, V, ρ, neighbor_ids, distances, α, β, h, c)

  ## Verlet advection scheme part 2
  _, V = half_verlet_scheme(X, V, F, dt)

  rhos[t, :] = ρ
  trajs[t, :, :] = X
  vels[t, :, :] = V

  print("Time step: ", t, "\tMax vels: ", np.max(V), "\tMin vels: ", np.min(V))

print("****************  Simulation COMPLETE  *************")

# %%

print("**************** Visualising the particle flow ***************")

speeds = np.linalg.norm(vels, axis=-1)

red_blue = np.ones_like(speeds)
red_blue[:, speeds.shape[1]//2:] = 0.0

visualise_sph_trajectory(trajs, 
                        # ("Speeds", speeds),
                        ("", red_blue),
                        DATAFOLDER+"trajectory.mp4", 
                        duration=15, 
                        domain_lim=D_LIM, 
                        vmin=None, vmax=None)

print("****************  Visualisation COMPLETE  *************")

# %%

## Save files


# print(" ****************** Saving data files ***********************")

# pos_path = DATAFOLDER+f"trajs_N{N}_T{T}_dt{dt}_ts{t_save}_h{h}_{IC}_θ{θ}.npy"
# vel_path = DATAFOLDER+f"vels_N{N}_T{T}_dt{dt}_ts{t_save}_h{h}_{IC}_θ{θ}.npy"
# rho_path = DATAFOLDER+f"rhos_N{N}_T{T}_dt{dt}_ts{t_save}_h{h}_{IC}_θ{θ}.npy"

# np.save(pos_path, trajs[t_save:,:,:])
# np.save(vel_path, vels[t_save:,:,:])
# np.save(rho_path, rhos[t_save:,:])

# print("****************  Saving COMPLETE  *************")



print(np.max(vels), np.min(vels))

# %%

