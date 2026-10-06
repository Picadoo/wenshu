---
noteType: article
paper: "[[Jaganathan2023 Basset历史力适用性与数值进展]]"
tags:
  - p2o/sub
---
> 返回索引：[[Jaganathan2023 Basset历史力适用性与数值进展]]

> © 2023 Divya Jaganathan, S. Ganga Prasath, Rama Govindarajan and Vishal Vasan. Originally published in Frontiers in Physics 11:1167338, https://doi.org/10.3389/fphy.2023.1167338, under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/. This Markdown transcription and figure crop are adapted for the software example; the original PDF retains the publisher’s copyright statement.

# The Basset–Boussinesq history force: its neglect, validity, and recent numerical developments

**Divya Jaganathan, S. Ganga Prasath, Rama Govindarajan, Vishal Vasan**

International Centre for Theoretical Sciences, Tata Institute of Fundamental Research, Bengaluru, India

Department of Applied Mechanics, Indian Institute of Technology Madras, Chennai, India

*Frontiers in Physics 2023, 11: 1167338. DOI: 10.3389/fphy.2023.1167338*

## Abstract

Particle-laden flows are ubiquitous, ranging across systems such as platelets in blood, dust storms, marine snow, and cloud droplets. The dynamics of a small particle in such non-uniform flows, under the idealization of being rigid and spherical, is described by the Maxey–Riley–Gatignol equation, which includes the Basset–Boussinesq history force among other better-understood forces. The history force, which is an integral over time with a weakly singular kernel, is often neglected, not because such neglect is known to be justified, but because it is difficult to be included in general scenarios. It is becoming increasingly evident that there are situations where neglecting this force might not be valid. In this review, after introducing classical knowledge about the history force, we outline recent studies that suggest alternative forms for it and discuss the range of validity of each, and describe recent numerical methods that have been developed to efficiently compute the history force. The question of whether the history force matters requires careful consideration and can be settled only with its accurate inclusion. We hope this review will help researchers addressing the multitude of open questions related to particulate flows to account for this effect.

## Keywords

particulate flow, Maxey–Riley equation, unsteady Stokes flow, Basset-Boussinesq history force, memory force

## 1 Introduction

Inertial (finite-sized) particles in fluid exhibit complex dynamics due to finite-time relaxation to the surrounding flow, allowing excursions from the underlying flow trajectory, unlike idealized passive particles (tracers) that instantaneously relax to the flow. Consequently, in multi-particle systems, such as planktons in oceans and aerosols in air, inertial particles can accumulate in certain regions of the flow, a tendency known as preferential concentration. Understanding such phenomena warrants an accurate description of particle motion. Customarily, the motion of an isolated inertial particle in non-uniform flows, under idealizations specified later, is modeled by the Maxey–Riley–Gatignol equation (MRG), which comprises a balance of different hydrodynamic forces[1, 2]. This article focuses on one such force in this balance—the Basset–Boussinesq history force (BBH) and its potential relevance in describing particle motion accurately.

There are notable qualitative differences when BBH is neglected in the model even in the simplest scenarios; a small sphere in a quiescent fluid, either relaxing freely (no external forcing) or approaching terminal velocity under gravity, does so algebraically when BBH is included (Basset[3]¹, Belmonte et al.[4], Farazmand and Haller[5], Prasath et al.[6]), as opposed to exponentially when excluded. This algebraic behavior is consistent with short-time experimental observations made by Mordant and Pinton[7] on a sphere settling under gravity. Similarly, a colloidal particle in fluid displaying long-time tails in velocity auto-correlations[8, 9] is supported in theory by inclusion of the history force[10–13]. A marginally heavy particle in a simulation without BBH is ejected from a solid-body vortex more rapidly than observed in experiment[14, 15]; whereas inclusion of BBH provides better agreement with the experiment. Exceptionally, Sapsis et al.[16] reported that while certain aspects of the dynamics of neutrally buoyant particles in the chaotic flow observed by Ouellette et al.[17] are predicted by MRG, any deterministic force including BBH is inadequate to capture random fluctuations.

> ¹ Basset credits and summarizes Signor Bogglio’s calculation for particle falling under gravity.

Numerical simulations too have highlighted the role of BBH in particle dynamics in chaotic/turbulent flows[18–28]. The main conclusions of these studies are (i) particle clustering and caustic formation are strongly reduced by BBH; (ii) in a typical chaotic flow without external forcing, particle attractors are less typical in the presence of BBH for light particles and the basin of attractions where particulate matter tends to aggregate shrinks irrespective of the particle’s Stokes number (ratio of particle relaxation timescale to flow timescale). Convergence to the attractors that remain is algebraically slower with BBH as opposed to exponential convergence in its absence; however, (iii) several statistical properties of particles remain unchanged. For example, the standard deviation $\sigma$ of trajectories of a collection of sedimenting particles has a ballistic scaling, $\sigma^2 \sim t^2$ for short times and diffusive, $\sigma^2 \sim t$ for long times, both with and without BBH. Nevertheless, individual trajectories of the particles show deviation. Yet, as Haller[29] summarizes the collective viewpoint, BBH “is notoriously difficult to handle, which prompts most studies to ignore this term despite ample numerical and experimental evidence of its significance.”

The MRG primarily models rigid, spherical particles that are small enough compared to the length-scales in the flow and in dilute enough suspension that one may neglect inter-particle interactions and assume one-way coupling, i.e., neglect the effect of particle on fluid flow. Thus each particle can be modeled as an isolated particle in an unbounded domain. Furthermore, it assumes that the particle induces only a weak disturbance flow, $w_d = (v - u)$, where $u$ is the undisturbed flow and $v$ is the disturbed flow due to the particle. This allows a creeping flow theory for the disturbance field wherein the particle Reynolds number, $Re_p = W_s a/\nu$, which is based on a characteristic particle slip velocity $W_s$ (a scale for the difference between particle and local flow velocities), particle radius $a$, and fluid kinematic viscosity $\nu$, and the shear-based Reynolds number, $Re_s = a^2 s/\nu$, where $s$ is the typical flow gradient, remain small throughout the motion. The forces experienced by the particle starting from rest relative to the flow under these assumptions are the Stokes and pressure drag, the added mass, and BBH, which appear in the following non-dimensional form of MRG (Faxén corrections are omitted for small enough particle)

$$
\frac{d x_p}{dt} = w_s + u(x_p),
\tag{1a}
$$

$$
\frac{d w_s(t)}{dt} = -\alpha w_s - \gamma \int_0^t \frac{1}{\sqrt{\pi(t-\tau)}} \frac{d w_s(\tau)}{d\tau}\, d\tau + N\bigl(u(x_p), w_s\bigr),
\tag{1b}
$$

where

$$
\alpha \equiv \frac{1}{RS},\qquad \gamma \equiv \sqrt{\frac{3}{R^2 S}},\qquad S \equiv \frac{1}{3}\frac{a^2}{\nu T},\qquad R \equiv \frac{1+2\beta}{3}.
$$

$$
N\bigl(u(x_p), w_s\bigr) = \left(\frac{1}{R}-1\right)\frac{Du}{Dt}\Big|_{x_p} - w_s \cdot \nabla u\big|_{x_p}.
$$

Here, $x_p(t)$ and $w_s(t)$ are the particle’s instantaneous position vector and slip-velocity ($\equiv \dot{x}_p(t) - u(x_p)$) respectively; $u(x, t)$ represents the non-uniform fluid velocity; $\beta$, which appears in the non-dimensional quantity $R$, denotes the particle-to-fluid density ratio; and $S$ is the Stokes number based on an appropriately chosen timescale $T$. The non-linear function $N$ includes added mass and pressure drag. The integral term on the right-hand side of Eq. 1b represents BBH—the standard form of history force with the Basset kernel, $K_B \equiv 1/\sqrt{\pi t}$.

The relative importance of competing forces in Eq. 1b depends on the particle-to-fluid density ratio ($R$), the local particle-to-flow response-time ratio ($S$), and the Reynolds numbers. Conventional arguments based on the density ratio suggest that BBH is as important as Stokes drag for marginally heavy ($R \sim 1$) particles, whereas it is negligible for particles much heavier than the fluid ($R \to \infty$), although the latter is valid only for a point particle. Scaling analysis of Eq. 1b reveals that for a finite-sized particle, the relative strength of Stokes drag and BBH is independent of the density ratio; rather it depends on the particle-to-flow response timescale ratio ($S$)[22, 30, 31]. The particle Reynolds number alters the strength of the history force fundamentally through the functional form of the kernel.

To aid the upcoming discussion on variants of the history kernel and numerical methods, it is useful to identify the force in a generalized form:

$$
F_h(t) = -\int_0^t K(t-\tau, w_s) \frac{d w_s}{d\tau}\, d\tau,
\tag{2}
$$

where $K$ is the general history kernel which reduces to $K_B(t) \equiv 1/\sqrt{\pi t}$ for BBH.

## 2 Developments in theory: History kernel

Theoretical studies show that the functional form of the history kernel can deviate from the standard form based on the underlying physics. Several variants under different conditions including high Reynolds number and initial accelerating/decelerating wake structures around the particle have been derived (see reviews by[32–34]). We selectively discuss two physical aspects driving the departure from the standard kernel within the creeping flow limit ($Re_s$, $Re_p \ll 1$): the late-time onset of advective/convective inertial dynamics for a rigid particle, and the magnitude of slip at the particle–fluid interface.

### 2.1 Late-time onset of advective/convective inertial effects for rigid particle

In the creeping flow limit, inertial timescales are slow and well-separated from the faster diffusive timescale, $\tau_v \approx a^2/\nu$. However, a particle accelerating through the fluid progresses through a range of timescales during which inertial effects could become important. This warrants a measure of the timescale of interest ($\tau^*$) relative to an inertial timescale ($\tau_i$) given by the Strouhal number $Sl = \tau_i/\tau^*$. Typically, either the particle convective time $a/W_s$ ($\tau_p$) or the inverse of the flow gradient $1/s$ ($\tau_s$) is taken as representative of the inertial timescale, while $\tau^*$ depends on the regime under consideration. For a non-uniform undisturbed flow, the non-dimensional Navier–Stokes equation for the disturbance field, in a frame translating with the particle, is

$$
Re_i\, Sl\, \frac{\partial w_d}{\partial t} + Re_s\, (w_d \cdot \nabla u) + Re_p\, (w_{ud} \cdot \nabla w_d + w_d \cdot \nabla w_d) = -\nabla p_d + \nabla^2 w_d,
\tag{3}
$$

where $w_{ud}(r) \equiv (u(x) - \dot{x}_p(t))$ is the known undisturbed field observed from the moving frame, $Re_i = a^2/\nu\tau_i$ is either $Re_p$ or $Re_s$ depending on the applicable inertial timescale, and the gradients are spatial derivatives taken with respect to the instantaneous coordinate, $r = x - x_p(t)$. In Eq. 3, distances have been scaled by $a$, time (where it explicitly appears) by $\tau^*$, velocity by $W_s$, and gradient of undisturbed field by $s$. The Strouhal number indicates the importance of the unsteady-inertia term $|\partial w_d/\partial t|$ relative to the shear-induced inertia term and the convective terms given in parentheses in Eq. 3.

Early-time diffusive dynamics: For a particle starting from rest in a homogeneous time-dependent flow, $u = u(t)$, Boussinesq[35] and Basset[36] showed that at early times, when $\tau^* \sim \tau_v$, the leading-order dynamics is governed by the unsteady Stokes equation, resulting in the history force with the Basset kernel (see Eq. 1b). Maxey and Riley[1] and Gatignol[2] derived the same history kernel for non-uniform flows, $u = u(x, t)$. Thus, for $Re_i Sl \sim O(1)$ corresponding to early time and the MRG model, the normalized history force $F_h(t)$ is given by

$$
F_h(t) = -6\pi \int_0^t \frac{1}{\sqrt{\pi(t-\tau)}} \frac{d w_s(\tau)}{d\tau}\, d\tau \eqqcolon -6\pi F_{BBH}(t),
\tag{4}
$$

where $t$ has been scaled by $\tau^* = \tau_v$.

Late-time advective/convective dynamics: At later times when $\tau^* \sim \tau_i$, inertial effects emerge either through convection or shear-induced advection corresponding to the following two limits:

(i) Oseen limit, $Re_s^{1/2} \ll Re_p < 1$, when $\tau^* \sim \nu/W_s^2 \gg \tau_v$ and $Sl \sim O(Re_p)$. Mei and Adrian[37]; Lovalenti and Brady[38] showed deviation from the MRG model with a kernel decaying faster than the standard kernel (Eq. 4). This is attributed to the development of spatially distinct inner and outer regions for the disturbance field (similar to the classical steady Oseen problem). In the outer region characterized by the Oseen distance $r \sim Re_p^{-1}$, the convective inertial terms become as important as the viscous terms, while in the inner region $r \sim 1$, close to the particle surface, a steady Stokes flow develops. This suggests that in sufficiently long time, vorticity generated at the particle’s surface escapes to the Oseen distance where convection becomes the primary mode of transport. Mei and Adrian[37] proposed the following semi-empirical form for the history force that uniformly captures both early- and late-time behaviors,

$$
F_h(t) \approx -6\pi Re_p \int_0^t \bigl[(\pi(t-\tau))^{1/4} + f(Re_p, t)\,(t-\tau)\bigr]^{-2} \frac{d w_s(\tau)}{d\tau}\, d\tau,
\tag{5}
$$

where $t$ is scaled by $\tau^* \equiv \nu/W_s^2$, and $f(Re_p, t)$ is a well-defined function, which notably breaks the convolution form of the history force owing to the explicit dependence on the current time. The kernel in Eq. 5 reduces to the standard kernel at short times ($t \to 0$).

(ii) Saffman-limit, $Re_p \ll Re_s^{1/2} < 1$. Candelier et al.[39,40] introduced linear flow inhomogeneity of the form $u(x, t) \equiv U(t) + A \cdot x$ to study the force on the particle due to shear-induced inertia. Here, $A$ is a time- and space-independent velocity-gradient tensor with a characteristic strain rate $s$. When $\tau^* \sim 1/s$ and $Sl \equiv O(1)$, an outer region develops at $r \sim Re_s^{-1/2}$, yielding the following history force up to the second order in the small parameter $Re_s^{1/2}$:

$$
F_h(t) = -6\pi Re_s^{1/2} \int_0^t K(t-\tau) \frac{d w_s}{d\tau}\, d\tau + Re_s \int_0^t K(t-\tau) \cdot \frac{d}{d\tau}\left(\int_0^\tau K(\tau-\sigma) \frac{d w_s}{d\sigma}\, d\sigma\right) d\tau,
\tag{6}
$$

where $t$ is scaled by $\tau^* = 1/s$ and $K$ is a flow-dependent kernel tensor. At early times, the tensor becomes diagonal with the elements recovering the standard kernel (Eq. 4). Finite-time corrections result in gradual development of both diagonal (drag force) and off-diagonal elements (shear-induced lift forces) with the specific form being flow-dependent.

We present the Saffman-limit and Oseen-limit separately in our schematic in Figure 1, but in actual flows, they could appear in complex combinations.

![Jaganathan2023 Basset历史力适用性与数值进展_page4_fig1.png](/vault/papers/jaganathan2023basset/images/Jaganathan2023%20Basset%E5%8E%86%E5%8F%B2%E5%8A%9B%E9%80%82%E7%94%A8%E6%80%A7%E4%B8%8E%E6%95%B0%E5%80%BC%E8%BF%9B%E5%B1%95_page4_fig1.png)

**Fig. 1.** Spatio-temporal landscape of the leading-order physics in (i) the Oseen limit, $Re_s^{1/2} \ll Re_p < 1$, and (ii) the Saffman limit, $Re_p \ll Re_s^{1/2} < 1$. The triplets $(\circ, \circ, \circ)$ in the figure indicate the relative strengths of the inertial terms, in the order unsteady ($|\partial w_d/\partial t|$), shear-advective ($|w_d \cdot \nabla u|$), and slip-convective ($|w_d \cdot \nabla w_d|$) inertia, compared to the viscous terms ($|\nabla^2 w_d| \sim |\nabla p_d|$). Asterisks denote dimensional quantities. Note in either limit, at later times, distinct “inner” and “outer” regions in space develop, and deviation from the standard kernel (Eqs. 5,6) is attributed to this. However, at short times, the diffusive unsteady Stokes equation drives the dynamics uniformly in space, yielding the standard Basset kernel. Idea courtesy: The schematic representation is inspired from Bentwich and Miloh[60] and Sano[59].

### 2.2 Kernels for slipping particle

The term “slip” is used to denote the difference in the particle’s velocity and the undisturbed flow velocity at the particle’s position. This is mere terminology, and in fact, the drag for rigid particles is derived with the imposition of the no-slip boundary condition at the particle–fluid interface. When some slippage is permitted as on a hydrophobic object, a modified history force emerges. Gatignol[41] provided the history kernel $K(t) \equiv (\exp\{t\nu/(a^2\delta^2)\}\mathrm{erfc}\{\sqrt{t\nu}/(a\delta)\})/\delta$, where $\delta$ is a slip-parameter. The standard kernel for no-slip is recovered when $\delta \to 0$. Effects of similar non-Basset-type kernels on partial-slip particles were also studied by Premlata and Wei[42].

Yang and Leal[43] and Galindo and Gerbeth[44] derived the hydrodynamic force on an accelerating spherical drop (viscosity $\mu_d$) in a quiescent fluid (viscosity, $\mu$). The modified history kernel for the drop has the form $K_B(t; \mu_d/\mu) + K_{\mathrm{new}}(t; \mu_d/\mu)$, where $K_{\mathrm{new}}$ is distinguished by its temporally non-monotonic behavior. Unlike the standard kernel, which is singular at initial time, the new kernel is always finite. On the other hand, both kernels have similar long-time behavior. For $\mu_d/\mu \to 0$ corresponding to a shape-preserving ‘bubble’, the kernel reduces to the form observed in Gatignol[41] with $\delta = 1/3$. Experiments by[45, 46] provide evidence to the short-time validity of the aforementioned forms of the history kernel for slipping particles (drops and bubbles).

## 3 Developments in numerics

The previous discussion shows that the form of the history force is tied to the underlying physics; nevertheless, it always assumes a generalized form (Eq. 2), and particularly the singular BBH form (Eq. 4) for rigid particles as $t \to 0$. In this section, we discuss the peculiarities associated with BBH (treating it as the model form) and report on the progress made in building numerical methods to solve the equation (1b). Most of the methods discussed can be adapted to other history kernels, especially when they are of the form $K_B(t) + K_{\mathrm{new}}(t)$, where $K_{\mathrm{new}}$ is a well-behaved function with no singularity. However, the construction of general-purpose methods to handle various singular kernels is still an active area of research.

### 3.1 The standard Basset kernel

For arbitrary initial slip-velocity, the modified BBH force (Eq. 4) at time $t$ is

$$
\frac{w_s(0)}{\sqrt{\pi t}} + \int_0^t \frac{1}{\sqrt{\pi(t-\tau)}} \frac{d w_s(\tau)}{d\tau}\, d\tau.
\tag{7}
$$

The first term imparts an initial-time singularity for non-zero particle slip-velocities. Often in numerical implementations, this term is avoided by imposing an unphysical zero initial slip-velocity. In general, we expect an initial slip-velocity for the inertial particle due to its finite-time response to the flow. In an equivalent representation[47], the modified BBH can be expressed in terms of the Riemann–Liouville half-derivative,

$$
\frac{d}{dt}\int_0^t \frac{w_s(\tau)}{\sqrt{\pi(t-\tau)}}\, d\tau \eqqcolon \frac{d^{1/2} w_s(t)}{dt^{1/2}}.
\tag{8}
$$

The connection to the half-derivative (Eq. 8) forms the basis for the schemes discussed in the following Section 3.2. A common feature of both representations (Eqs 7, 8) is the non-locality in time. For BBH, the non-locality is expressed as a convolution of the standard kernel with the history of particle-states. It should be noted that the state at time $t$ enforces the most “vivid” memory-effect due to the current-time singularity of the kernel, while the impact of past states decays algebraically with elapsed time.

The form of the kernel and the non-locality-in-time imply that MRG is not a dynamical system[5, 6]: the particle position and velocity at time $t$ are insufficient to uniquely determine the path of the system in position-velocity space. This fact precludes the use of standard numerical ODE-integrators, and the task of computing the history integral at each time-step is unavoidable. Computing the history integral entails (i) a memory requirement to store all past states and (ii) an operational cost to compute the convolution. As one evolves the system forward in time, both memory requirement and operational cost increase. Indeed, if we evolve the system through discrete times $\{t_N = N\Delta t\}$, where $\Delta t$ is the step size, the operational cost increases quadratically with the number of time steps ($\sim O(N^2)$) and the memory requirement increases linearly ($\sim O(N)$). These increasing costs are the reason why many simply neglect the history force (justifiably or otherwise) in Eq. 1b, thereby obtaining a dynamical system. On the other hand, the approaches we discuss in the following section do account for the history effect.

### 3.2 Overview of numerical approaches

We classify numerical solution approaches by identifying the overarching strategy used to address the computational challenges described in Section 3.1, into the following categories (subsections). An earlier review by Moreno-Casas and Bombardelli[48] supplements this overview as we also discuss approaches developed since.

#### 3.2.1 Full quadrature

Daitche[47] developed a general scheme to compute the BBH integral to arbitrarily high degrees of accuracy. Using the expression (Eq. 8), the integrated form of MRG may be written as follows:

$$
w_s(t_{n+1}) = w_s(t_n) + \Biggl[\int_0^{t_{n+1}} K_B(t_{n+1}-\tau)\, w_s(\tau)\, d\tau - \int_0^{t_n} K_B(t_n-\tau)\, w_s(\tau)\, d\tau\Biggr] + \int_{t_n}^{t_{n+1}} \bigl(-\alpha w_s(\tau) + N(w_s(\tau))\bigr)\, d\tau.
\tag{9}
$$

Quadrature routines involve polynomial interpolation of the integrand and require evaluation of the integrand at the limits of the integral. Hence, Daitche[47] employed a Lagrange-polynomial interpolant only for the slip-velocity, retaining the kernel (and singularity) as it is. The resulting integrals are then evaluated exactly. Here, the degree of the interpolating polynomial determines the order of accuracy. The quadrature is given by

$$
\int_0^{t_n} K_B(t_n-\tau)\, w_s(\tau)\, d\tau = \sum_{m=1}^{n} \int_{t_{m-1}}^{t_m} K_B(t_n-\tau)\, w_s(\tau)\, d\tau \approx \sqrt{\Delta t} \sum_{m=1}^{n} \mu_m^n w_s(t_{n-m}),
\tag{10}
$$

where $\{\mu_m^n\}$ are scheme-specific, time-dependent weights which can be pre-computed and are explicitly provided by Daitche[47] for $O(\Delta t)$, $O(\Delta t^2)$, $O(\Delta t^3)$-accurate schemes. The need to retain the slip-velocities in the past to compute the quadrature persists. Hence, we must accept the increasing memory and operational cost. However, higher-accuracy schemes come at essentially no additional cost.

Another class of full quadrature schemes, of varying accuracy, designed specifically for fractional–differential equations are described in the works of Garrappa and Popolizio[49]; Garrappa[50]. These methods are similar to exponential integrators introduced by Cox and Matthews[51] but adapted to fractional derivatives.

#### 3.2.2 Window-based approaches

This class of methods involves splitting the integral in Eq. 7 into one over the distant past and another for the recent past. The motivation is to accurately treat the current-time singularity, while approximating the history kernel in the distant past to reduce operational costs. A general construction is given by

$$
F_{BBH}(t_n) \coloneqq \int_0^{t_n} K_B(t_n-\tau) \frac{d w_s(\tau)}{d\tau}\, d\tau \approx F_{\mathrm{tail}}(t_n) + F_{\mathrm{win}}(t_n),
\tag{11}
$$

where

$$
\begin{aligned}
F_{\mathrm{tail}}(t_n) &= \int_0^{t_n-t_{\mathrm{win}}} K_{\mathrm{tail}}(t_n-\tau) \frac{d w_s(\tau)}{d\tau}\, d\tau,\\
F_{\mathrm{win}}(t_n) &= \int_{t_n-t_{\mathrm{win}}}^{t_n} K_{\mathrm{win}}(t_n-\tau) \frac{d w_s(\tau)}{d\tau}\, d\tau.
\end{aligned}
\tag{12}
$$

Here, $t_{\mathrm{win}} = M\Delta t$ is the recent-past window size. The studies reviewed here are essentially distinguished by their choice of $K_{\mathrm{win}}$, $K_{\mathrm{tail}}$.

As the current-time singularity always occurs in the window $[t_n - t_{\mathrm{win}}, t_n]$, the form of the kernel (hence singularity) is usually retained in this window. One sets $K_{\mathrm{win}}(\circ) = K_B(\circ)$ and thereafter employs a quadrature scheme similar to Daitche[47]. For instance, Brush et al.[52] assumed constant slip-acceleration, whereas van Hinsberg et al.[53] used a linear interpolant of the slip-acceleration. In another instance, instead of constructing a quadrature, Bombardelli et al.[54] approximated the integral in the recent time window by the series representation of the Riemann–Liouville half-derivative.

In the tail window $[0, t_n - t_{\mathrm{win}}]$, one seeks fast-converging approximate kernels. Dorgan and Loth[55] and Bombardelli et al.[54] completely ignored the tail, effectively truncating the integral by setting $K_{\mathrm{tail}}(\circ) = 0$. On the other hand, a new class of exponential methods emerged, e.g., van Hinsberg et al.[53], where $K_{\mathrm{tail}}(\circ)$ is given by a sum of decaying exponentials that approximate $K_B$ in $[0, t_n - t_{\mathrm{win}}]$. The resulting tail integral for method-specific positive constants $\{a_i, t_i\}$ and known functional forms of $\{\alpha, \beta\}$ is given by

$$
F_{\mathrm{tail}}(t_n) = \sum_{i=1}^{m} F_i(t_n) = \sum_{i=1}^{m} \int_0^{t_n-t_{\mathrm{win}}} a_i K_i(t_n-\tau) \frac{d w_s(\tau)}{d\tau}\, d\tau = \int_0^{t_n-t_{\mathrm{win}}} a_i \alpha(t_i)\, e^{-\beta(t_i)(t_n-\tau)} \frac{d w_s(\tau)}{d\tau}\, d\tau.
\tag{13}
$$

In particular,

$$
F_i(t_n) = e^{-\beta(t_i)\Delta t} F_i(t_n-\Delta t) + a_i \alpha(t_i) \int_{t_n-t_{\mathrm{win}}-\Delta t}^{t_n-t_{\mathrm{win}}} e^{-\beta(t_i)(t_n-\tau)} \frac{d w_s(\tau)}{d\tau}\, d\tau.
\tag{14}
$$

Note that the recursive nature of this method in its treatment of the tail integral is a consequence of the exponential-form approximation. This suggests $F_i(t)$ are dynamical variables that satisfy linear equations forced by the slip-acceleration. Parmar et al.[56] essentially pursued this idea to obtain a differential equation for each approximate force $F_i(t)$. The quadrature is significantly curtailed by requiring small $t_{\mathrm{win}}$, and the exponential approximation is obtained following Beylkin and Monzón[57], but otherwise their method is similar to that previously described.

For window-based approaches, the parameter $t_{\mathrm{win}}$ must be chosen carefully, and often the criterion is problem-specific. For the physical system of interest in Bombardelli et al.[54], $t_{\mathrm{win}}$ is determined based on the time beyond which the particle-state correlations are observed to be weak. However, van Hinsberg et al.[53] and Parmar et al.[56] set up a minimization problem for an error-like quantity to determine their optimal $t_{\mathrm{win}}$. Casas et al.[58] improved the optimization for van Hinsberg et al.[53]’s approach.

#### 3.2.3 Formulation as a partial differential equation

A different approach was introduced by Prasath et al.[6], who showed that the governing MRG, in its entirety, can be posed as a dynamic boundary condition for a suitable 1D diffusion equation over a half-line—a system for which much is known and solvable. Prasath et al.[6] essentially exploited the fact that the Dirichlet–Neumann operator for the diffusion equation is (up to a sign) the Riemann–Liouville half-derivative, whereas the window-based methods hinted at or constructed dynamical systems that approximate MRG; Prasath et al.[6] described an exact reformulation of MRG that is local-in-time. Indeed, they defined a diffusing quantity $q(\zeta, t)$ in a pseudo-space coordinate $\zeta > 0$. The slip-velocity $w_s(t)$ is related to $q$ by $q(0, t) \coloneqq w_s(t)$. Under these definitions, they proposed the following system:

$$
q_t = q_{\zeta\zeta},
\tag{15a}
$$

$$
q(\zeta > 0,\ t = 0) = 0,
\tag{15b}
$$

$$
q_t(0, t) + \alpha q(0, t) - \gamma q_\zeta(0, t) = N\bigl(q(0, t),\ u(x_p(t))\bigr),
\tag{15c}
$$

$$
\lim_{t \to 0} q(0, t) = w_s(0),
\tag{15d}
$$

where $q_\zeta(0, t)$ represents the BBH term, and the subscripts $t$ and $\zeta$ refer to partial derivatives. Indeed, MRG (Eq. 15c) manifests as a generalized Robin boundary condition.

Using the aforementioned reformulation, one derives an expression for $q(0, t)$ (equivalently the slip-velocity) for $t_n < t \le t_{n+1}$ given $q(0, t_n)$, with the introduction of a new (dynamical) quantity called the ‘history function’, denoted by $H(k, t)$,

$$
-\frac{\pi}{2} q(0, t) = \int_0^{\infty} e^{-k^2(t-t_n)}\,\mathrm{Im}\bigl(k H(k, t_n)\bigr)\, dk + \int_0^{t-t_n} N\bigl(q(0, t_n+\tau)\bigr) \times \int_0^{\infty} \mathrm{Im}\left[\frac{k e^{-k^2(t-t_n-\tau)}}{ik\gamma - k^2 + \alpha}\right] dk\, d\tau,
\tag{16a}
$$

$$
H(k, t_{n+1}) = e^{-k^2\Delta t} H(k, t_n) - \int_0^{\Delta t} e^{-k^2(\Delta t-\tau)} \frac{q(0, t_n+\tau) + N\bigl(q(0, t_n+\tau)\bigr)}{ik\gamma - k^2 + \alpha}\, d\tau.
\tag{16b}
$$

At $t = 0$, the history function is known analytically, and for $t_n > 0$, $H(k, t_n)$ is represented using Chebyshev polynomials. One assumes the slip-velocity $q(0, t)$, $t \in [t_n, t_{n+1}]$ also has a Chebyshev expansion. Given $H(k, t_n)$, Prasath et al.[6] solved Eq. 16a using the Newton method for the Chebyshev coefficients of $q(0, t)$. Then, they updated the history using Eq. 16b to solve for the slip-velocity in the next time-step. The highlight of the scheme is that no approximation is made to the kernel. Moreover, by including $H(k, t)$ as a dynamical variable, the operational cost, the memory requirement, and cost to restart the simulation become independent of time.

In summary, the choice of the numerical approach would depend on available computational resources and the required accuracy. In Table 1, we provide a comparison of approaches based on how computational expenses increase with simulated time ($\sim N$). The costs are scaled by a method-dependent prefactor, suggesting a break-even point between the cost and simulated time, where one method outperforms another. Briefly,

- for short-duration simulations (small memory build-up), the quadrature approach with its scalable accuracy and nominal cost for short times is a reasonable choice;
- for kernels with fast decay (e.g., (Eq. 5)), window-based approaches are a computationally relieving alternative;
- for long-time and multi-particle simulations, where little can be said about the dynamics a priori, such as particles in turbulence, partial differential reformulation guarantees accuracy without growing-in-time computational costs.

**Table 1.** Computational demands such as memory storage requirement, operational cost (FLOPs), and the corresponding accuracy of different methods that capture the effects of BBH. $N\Delta t$ is the simulated time, and $M = t_{\mathrm{win}}/\Delta t$ is the number of time-steps in the recent-past window $t_{\mathrm{win}}$ (fixed a priori). The accuracy column indicates the order of accuracy obtained by the explicitly available schemes developed under each approach (see Section 3.2). The order of accuracy $O(\Delta t^p)$ used here indicates that the local error of the scheme scales as $O(\Delta t^{p+1})$.

| Approach | Memory storage | Operational cost | Accuracy |
| --- | --- | --- | --- |
| Full quadrature | $O(N)$ | $O(N^2)$ | $O(\Delta t)$, $O(\Delta t^2)$, $O(\Delta t^3)$ |
| Window-based methods (window $= M\Delta t$) | $O(N)$ if $N \lt M$; $O(M)$ if $N \ge M$ | $O(N^2)$ if $N \lt M$; $O(M^2)+O(N-M)$ if $N \ge M$ | $O(\Delta t^{1/2})$, $O(\Delta t)$ |
| PDE formulation | Constant | $O(N)$ | Spectral |

## 4 Summary and future directions

The ubiquity of inertial particles in non-uniform flows makes it important to develop accurate methods to obtain their dynamics. We have highlighted analytical and numerical studies which indicate that the inclusion of a history force in the model is important to describe transient dynamics observed in experiments, whereas statistical properties often remain unaffected by its inclusion. This requires further understanding. The computational barrier to simulating a large number of particles with history force has been progressively bridged by numerical strategies (Section 3.2), opening ways to numerically explore history effects in large-scale systems. However, a lack of consensus on the role and functional form of this force in general multi-scale flows provides an active area of research with several open questions. We list a few promising directions pertaining to history force:

- History force in turbulent flows. Existing theories for a single particle in a simple flow[37–40, 59] demonstrated how the history force changes its form due to the emergence of fundamentally different physics over multiple timescales. This compels enquiry into the history force on an inertial particle sampling spatio-temporally varying features in turbulence.
- Inter-particle hydrodynamic interactions and collision kernels. BBH (and MRG) is derived for an isolated particle, and by extension is valid for dilute suspensions. However, the form of the history force when particles approach each other has not been explored. Are there screening effects due to inter-particle interactions that supersede history effects? An associated question is when particles collide or droplets coalesce, how do their histories exchange or combine? Answers to these questions will inform accurate construction of collision kernels.

Interesting insights are likely to emerge one way or the other in finding whether the history force and its effects matter.

## Author Contributions

All authors listed have made a substantial, direct, and intellectual contribution to the work and approved it for publication.

## Funding

We acknowledge support of the Department of Atomic Energy, Government of India, under project no. RTI4001.

## Acknowledgments

We gratefully acknowledge inputs from Saumav Kapoor, ICTS-TIFR.

## Conflict of Interest Statement

The authors declare that the research was conducted in the absence of any commercial or financial relationships that could be construed as a potential conflict of interest.

## Publisher's Note

All claims expressed in this article are solely those of the authors and do not necessarily represent those of their affiliated organizations, or those of the publisher, the editors, and the reviewers. Any product that may be evaluated in this article, or claim that may be made by its manufacturer, is not guaranteed or endorsed by the publisher.

## References

1. Maxey MR, Riley JJ. Equation of motion for a small rigid sphere in a nonuniform flow. *Phys Fluids* (1983) 26:883–9. doi:10.1063/1.864230
2. Gatignol R. The Faxén formulae for a rigid particle in an unsteady non-uniform Stokes flow. *J Mec Theor Appl* (1983) 2:241–82.
3. Basset AB. (1910). On the descent of a sphere in a viscous liquid, 41
4. Belmonte A, Jacobsen J, Jayaraman A. Monotone solutions of a nonautonomous differential equation for a sedimenting sphere. *Electron J Diff Eqns* (2001) 2001:1–17.
5. Farazmand M, Haller G. The Maxey–Riley equation: Existence, uniqueness and regularity of solutions. *Nonlinear Anal Real World Appl* (2015) 22:98–106. doi:10.1016/j.nonrwa.2014.08.002
6. Prasath SG, Vasan V, Govindarajan R. Accurate solution method for the Maxey–Riley equation, and the effects of Basset history. *J Fluid Mech* (2019) 868:428–60. doi:10.1017/jfm.2019.194
7. Mordant N, Pinton J. Velocity measurement of a settling sphere. *Eur Phys J B* (2000) 18:343–52. doi:10.1007/pl00011074
8. Rahman A. Correlations in the motion of atoms in liquid Argon. *Phys Rev* (1964) 136:A405–11. doi:10.1103/physrev.136.a405
9. Alder BJ, Wainwright TE. Decay of the velocity autocorrelation function. *Phys Rev A* (1970) 1:18–21. doi:10.1103/physreva.1.18
10. Zwanzig R, Bixon M. Hydrodynamic theory of the velocity correlation function. *Phys Rev A* (1970) 2:2005–12. doi:10.1103/physreva.2.2005
11. Widom A. Velocity fluctuations of a hard-core Brownian particle. *Phys Rev A* (1971) 3:1394–6. doi:10.1103/physreva.3.1394
12. Hinch EJ. Application of the Langevin equation to fluid suspensions. *J Fluid Mech* (1975) 72:499–511. doi:10.1017/s0022112075003102
13. Clercx HJH, Schram PPJM. Brownian particles in shear flow and harmonic potentials: A study of long-time tails. *Phys Rev A* (1992) 46:1942–50. doi:10.1103/physreva.46.1942
14. Druzhinin O, Ostrovsky L. The influence of Basset force on particle dynamics in two-dimensional flows. *Physica D* (1994) 76:34–43. doi:10.1016/0167-2789(94)90248-8
15. Candelier F, Angilella JR, Souhar M. On the effect of the Boussinesq–Basset force on the radial migration of a Stokes particle in a vortex. *Phys Fluids* (2004) 16:1765–76. doi:10.1063/1.1689970
16. Sapsis TP, Ouellette NT, Gollub JP, Haller G. (2011). Neutrally buoyant particle dynamics in fluid flows: Comparison of experiments with Lagrangian stochastic models. *Phys Fluids* 23, 093304. doi:10.1063/1.3632100
17. Ouellette NT, O’Malley PJJ, Gollub JP. Transport of finite-sized particles in chaotic flow. *Phys Rev Lett* (2008) 101:174504. doi:10.1103/physrevlett.101.174504
18. Mei R, Adrian RJ, Hanratty TJ. Particle dispersion in isotropic turbulence under Stokes drag and Basset force with gravitational settling. *J Fluid Mech* (1991) 225:481–95. doi:10.1017/s0022112091002136
19. Elghobashi S, Truesdell GC. Direct simulation of particle dispersion in a decaying isotropic turbulence. *J Fluid Mech* (1992) 242:655–700. doi:10.1017/s0022112092002532
20. Armenio V, Fiorotto V. The importance of the forces acting on particles in turbulent flows. *Phys Fluids* (2001) 13:2437–40. doi:10.1063/1.1385390
21. van Aartrijk M, Clercx HJH. Vertical dispersion of light inertial particles in stably stratified turbulence: The influence of the Basset force. *Phys Fluids* (2010) 22:013301. doi:10.1063/1.3291678
22. Daitche A, Tél T. Memory effects are relevant for chaotic advection of inertial particles. *Phys Rev Lett* (2011) 107:244501. doi:10.1103/physrevlett.107.244501
23. Calzavarini E, Volk R, Lévêque E, Pinton J-F, Toschi F. Impact of trailing wake drag on the statistical properties and dynamics of finite-sized particle in turbulence. *Physica D* (2012) 241:237–44. doi:10.1016/j.physd.2011.06.004
24. Guseva K, Feudel U, Tél T. Influence of the history force on inertial particle advection: Gravitational effects and horizontal diffusion. *Phys Rev E* 88 (2013) 88:042909. doi:10.1103/physreve.88.042909
25. Olivieri S, Picano F, Sardina G, Iudicone D, Brandt L. The effect of the Basset history force on particle clustering in homogeneous and isotropic turbulence. *Phys Fluids* 26 (2014) 26:041704. doi:10.1063/1.4871480041704
26. Daitche A. On the role of the history force for inertial particles in turbulence. *J Fluid Mech* (2015) 782:567–93. doi:10.1017/jfm.2015.551
27. Guseva K, Daitche A, Feudel U, Tél T. History effects in the sedimentation of light aerosols in turbulence: The case of marine snow. *Phys Rev Fluids* 1 (2016) 1:074203. doi:10.1103/physrevfluids.1.074203
28. van Hinsberg MAT, Clercx HJH, Toschi F. Enhanced settling of nonheavy inertial particles in homogeneous isotropic turbulence: The role of the pressure gradient and the Basset history force. *Phys Rev E* 95 (2017) 95:023106. doi:10.1103/physreve.95.023106023106
29. Haller G. Solving the inertial particle equation with memory. *J Fluid Mech* (2019) 874:1–4. doi:10.1017/jfm.2019.378
30. Ling Y, Parmar M, Balachandar S. A scaling analysis of added-mass and history forces and their coupling in dispersed multiphase flows. *Int J Multiphase Flow* (2013) 57:102–14. doi:10.1016/j.ijmultiphaseflow.2013.07.005
31. Li Z, Wei J, Bu S, Yu B. A frequency analysis method to estimate the relative importance of Basset force on small particles in turbulence. *Int J Multiphase Flow* (2021) 139:103640. doi:10.1016/j.ijmultiphaseflow.2021.103640
32. Mei R. Velocity fidelity of flow tracer particles. *Exp Fluids* (1996) 22:1–13. doi:10.1007/bf01893300
33. Michaelides EE. Review—the transient equation of motion for particles, bubbles, and droplets. *ASME J Fluids Eng* (1997) 119:233–47. doi:10.1115/1.2819127
34. Magnaudet J, Eames I. The motion of high-Reynolds-number bubbles in inhomogeneous flows. *Annu Rev Fluid Mech* (2000) 32:659–708. doi:10.1146/annurev.fluid.32.1.659
35. Boussinesq J. Sur la résistance qu’oppose un liquide indéfini au repos au mouvement varié d’une sphère solide. *C R Acad Sci Paris* (1885) 100:935–7.
36. Basset A. *Treatise on hydrodynamics* (deighton, bell and company) (1888).
37. Mei R, Adrian R. Flow past a sphere with an oscillation in the free-stream velocity and unsteady drag at finite Reynolds number. *J Fluid Mech* (1992) 237:323–41. doi:10.1017/s0022112092003434
38. Lovalenti PM, Brady JF. The force on a sphere in a uniform flow with small-amplitude oscillations at finite Reynolds number. *J Fluid Mech* (1993) 256:607–14. doi:10.1017/s0022112093002897
39. Candelier F, Mehlig B, Magnaudet J. Time-dependent lift and drag on a rigid body in a viscous steady linear flow. *J Fluid Mech* (2019) 864:554–95. doi:10.1017/jfm.2019.23
40. Candelier F, Mehaddi R, Mehlig B, Magnaudet J. Second-order inertial forces and torques on a sphere in a viscous steady linear flow. *J Fluid Mech* (2023) 954:A25. doi:10.1017/jfm.2022.1015
41. Gatignol R. On the history term of Boussinesq–Basset when the viscous fluid slips on the particle. *Comptes Rendus Mécanique* (2007) 335:606–16. doi:10.1016/j.crme.2007.08.013
42. Premlata AR, Wei H-H. Atypical non-Basset particle dynamics due to hydrodynamic slip. *Phys Fluids* 32 (2020) 32:097109. doi:10.1063/5.0021986
43. Yang S, Leal LG. A note on memory-integral contributions to the force on an accelerating spherical drop at low Reynolds number. *Phys Fluids A* (1991) 3:1822–4. doi:10.1063/1.858202
44. Galindo V, Gerbeth G. A note on the force on an accelerating spherical drop at low-Reynolds number. *Phys Fluids A* (1993) 5:3290–2. doi:10.1063/1.858686
45. Abbad M, Souhar M. Experimental investigation on the history force acting on oscillating fluid spheres at low Reynolds number. *Phys Fluids* (2004) 16:3808–17. doi:10.1063/1.1779051
46. Garbin V, Dollet B, Overvelde M, Cojoc D, Di Fabrizio E, van Wijngaarden L, et al. History force on coated microbubbles propelled by ultrasound. *Phys Fluids* 21 (2009) 21:092003. doi:10.1063/1.3227903092003
47. Daitche A. Advection of inertial particles in the presence of the history force: Higher order numerical schemes. *J Comput Phys* (2013) 254:93–106. doi:10.1016/j.jcp.2013.07.024
48. Moreno-Casas PA, Bombardelli FA. Computation of the Basset force: Recent advances and environmental flow applications. *Environ Fluid Mech* (2016) 16:193–208. doi:10.1007/s10652-015-9424-1
49. Garrappa R, Popolizio M. Generalized exponential time differencing methods for fractional order problems. *Comput Math Appl* (2011) 62:876–90. doi:10.1016/j.camwa.2011.04.054
50. Garrappa R. Numerical solution of fractional differential equations: A survey and a software tutorial. *Mathematics* (2018) 6:16. doi:10.3390/math6020016
51. Cox SM, Matthews PC. Exponential time differencing for stiff systems. *J Comput Phys* (2002) 176:430–55. doi:10.1006/jcph.2002.6995
52. Brush LM, Ho H-W, Yen B-C. Accelerated motion of a sphere in a viscous fluid. *J Hydraul Eng* (1964) 90:149–60. doi:10.1061/jyceaj.0000973
53. van Hinsberg M, ten Thije Boonkkamp J, Clercx H. An efficient, second order method for the approximation of the Basset history force. *J Comput Phys* (2011) 230:1465–78. doi:10.1016/j.jcp.2010.11.014
54. Bombardelli F, González A, Niño Y. Computation of the particle Basset force with a fractional-derivative approach. *J Hydraul Eng* (2008) 134:1513–20. doi:10.1061/(asce)0733-9429(2008)134:10(1513)
55. Dorgan A, Loth E. Efficient calculation of the history force at finite Reynolds numbers. *Int J Multiphase Flow* (2007) 33:833–48. doi:10.1016/j.ijmultiphaseflow.2007.02.005
56. Parmar M, Annamalai S, Balachandar S, Prosperetti A. Differential formulation of the viscous history force on a particle for efficient and accurate computation. *J Fluid Mech* (2018) 844:970–93. doi:10.1017/jfm.2018.217
57. Beylkin G, Monzón L. On approximation of functions by exponential sums. *Appl Comput Harmon Anal* (2005) 19:17–48. doi:10.1016/j.acha.2005.01.003
58. Casas G, Ferrer A, Oñate E. Approximating the Basset force by optimizing the method of van Hinsberg et al. *J Comput Phys* (2018) 352:142–71. doi:10.1016/j.jcp.2017.09.060
59. Sano T. Unsteady flow past a sphere at low Reynolds number. *J Fluid Mech* (1981) 112:433–41. doi:10.1017/s0022112081000499
60. Bentwich M, Miloh T. The unsteady matched Stokes-Oseen solution for the flow past a sphere. *J Fluid Mech* (1978) 88:17–32. doi:10.1017/s0022112078001962
