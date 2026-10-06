---
noteType: article
paper: "[[Jaganathan2023 Basset历史力适用性与数值进展]]"
tags: ["p2o/sub"]
---
> 返回索引：[[Jaganathan2023 Basset历史力适用性与数值进展]]

> © 2023 Divya Jaganathan、S. Ganga Prasath、Rama Govindarajan 和 Vishal Vasan。原刊：Frontiers in Physics 11:1167338，https://doi.org/10.3389/fphy.2023.1167338；许可：CC BY 4.0，https://creativecommons.org/licenses/by/4.0/。本文为软件示例使用的 AI 辅助中文译文及排版改编，不是作者提供的中文原作；原 PDF 保留出版声明。

# Basset–Boussinesq历史力：忽略、有效性与近期数值进展

**Divya Jaganathan、S. Ganga Prasath、Rama Govindarajan、Vishal Vasan**

印度塔塔基础研究院国际理论科学中心（班加罗尔）；印度理工学院马德拉斯分校应用力学系（金奈）

*Frontiers in Physics, 2023, 11. DOI: 10.3389/fphy.2023.1167338*

## 亮点

- 面向血小板、沙尘暴、海洋雪、云滴等含颗粒流动，聚焦 Maxey–Riley–Gatignol 方程中的 Basset–Boussinesq 历史力。
- 指出历史力是一个带弱奇异核的时间积分；长期被忽略并非因为忽略有据，而是因为一般情形下纳入它十分困难。
- 综述历史力的经典认识，梳理提出替代表达式的近期研究并逐一讨论各自适用范围。
- 介绍为高效计算历史力而发展的各类数值方法。
- 强调「历史力是否重要」必须慎重考察，且只有准确纳入历史力之后才能判断。

> **【说明】** 本节要点由 AI 通读全文提炼，原刊未印 Highlights / Key Points。

## 摘要

含颗粒流动广泛存在于血液中的血小板、沙尘暴、海洋雪以及云滴等系统中。在将颗粒理想化为刚性球体的条件下，非均匀流动中小颗粒的动力学由 Maxey–Riley–Gatignol（MRG）方程描述；除若干理解较充分的作用力外，该方程还包含 Basset–Boussinesq 历史力。历史力是一个带弱奇异核的时间积分。人们经常忽略它，并非因为已有证据证明这种忽略合理，而是因为在一般情形下纳入该力十分困难。越来越多的证据表明，在某些情况下忽略历史力可能并不成立。

本文首先介绍历史力的经典认识，随后概述提出其替代表达式的近期研究并讨论各表达式的适用范围，最后介绍为高效计算历史力而发展的数值方法。“历史力是否重要”这一问题必须慎重考察，而且只有准确纳入历史力后才能作出判断。我们希望本综述能帮助研究各类含颗粒流动开放问题的学者考虑这一效应。

**关键词：** 含颗粒流动；Maxey–Riley 方程；非定常 Stokes 流；Basset–Boussinesq 历史力；记忆力

## 1 引言

流体中的惯性（有限尺寸）颗粒具有复杂动力学。由于颗粒需要有限时间才能松弛到周围流体的运动状态，它能够偏离作为基底的流体轨迹；理想化的被动颗粒（示踪粒子）则会瞬时松弛到流体速度。因此，在海洋浮游生物和空气气溶胶等多颗粒系统中，惯性颗粒可能在流场的某些区域聚集，这种倾向称为优先聚集。理解这类现象需要准确描述颗粒运动。按照惯例，在下文给出的理想化条件下，非均匀流动中孤立惯性颗粒的运动由 Maxey–Riley–Gatignol 方程（MRG）建模；该方程表示不同流体动力的平衡 [[#^ref-1|1]],[[#^ref-2|2]]。本文关注其中一种力——Basset–Boussinesq 历史力（BBH），以及它对于准确描述颗粒运动可能具有的重要性。

即使在最简单的情形中，忽略 BBH 也会产生显著的定性差异。静止流体中的小球，无论是无外力作用下自由松弛，还是在重力作用下趋近终端速度，纳入 BBH 时均以代数规律松弛 [[#^ref-3|3]]–[[#^ref-6|6]]，而排除 BBH 时则呈指数松弛。这种代数行为与 Mordant 和 Pinton [[#^ref-7|7]] 对重力沉降球体的短时间实验观测一致。同样，流体中胶体颗粒速度自相关的长时尾 [[#^ref-8|8]],[[#^ref-9|9]]，也得到包含历史力的理论 [[#^ref-10|10]]–[[#^ref-13|13]] 支持。对于边际重颗粒，不含 BBH 的模拟预测其从固体体旋涡中被抛出的速度快于实验结果 [[#^ref-14|14]],[[#^ref-15|15]]；纳入 BBH 后则与实验符合得更好。一个值得注意的例外是 Sapsis 等 [[#^ref-16|16]] 的报告：MRG 虽能预测 Ouellette 等 [[#^ref-17|17]] 观察到的混沌流中中性浮力颗粒动力学的某些方面，但包括 BBH 在内的任何确定性力都不足以捕捉随机涨落。

数值模拟同样突出了 BBH 在混沌流或湍流颗粒动力学中的作用 [[#^ref-18|18]]–[[#^ref-28|28]]。这些研究的主要结论是：

1. BBH 会显著削弱颗粒团簇和焦散的形成；
2. 在无外部强迫的典型混沌流中，加入 BBH 后，轻颗粒的颗粒吸引子更少见；无论颗粒 Stokes 数如何，颗粒物质倾向聚集的吸引域都会缩小。对仍然存在的吸引子，含 BBH 时以代数速度收敛，而不含 BBH 时呈指数收敛；
3. 但颗粒的若干统计性质并不改变。例如，一组沉降颗粒轨迹的标准差在短时间保持弹道标度 $\sigma^2\sim t^2$，在长时间保持扩散标度 $\sigma^2\sim t$，无论是否含 BBH 都是如此；不过，单个颗粒的轨迹仍会出现偏差。

正如 Haller [[#^ref-29|29]] 对这一共同观点的概括：BBH“极难处理，因此尽管已有充分的数值和实验证据表明它很重要，多数研究仍会忽略这一项”。

MRG 主要描述刚性球形颗粒，并要求颗粒相对于流动长度尺度足够小、悬浮体系足够稀，使颗粒间相互作用可以忽略，并可采用单向耦合，即忽略颗粒对流场的影响。这样，每个颗粒都可视为无界区域中的孤立颗粒。方程还假定颗粒仅诱导弱扰动流 $\boldsymbol w_d=\boldsymbol v-\boldsymbol u$，其中 $\boldsymbol u$ 为未扰动流场，$\boldsymbol v$ 为受颗粒影响后的流场。由此可对扰动场采用蠕动流理论，并要求整个运动过程中颗粒 Reynolds 数

$$
Re_p=\frac{W_s a}{\nu}
$$

以及基于剪切的 Reynolds 数

$$
Re_s=\frac{a^2s}{\nu}
$$

始终较小。这里，$W_s$ 是特征颗粒滑移速度，即颗粒速度与局部流体速度之差的尺度；$a$ 为颗粒半径，$\nu$ 为流体运动黏度，$s$ 为典型流动梯度。在这些假设下，从相对流体静止状态开始运动的颗粒受到 Stokes 阻力、压力阻力、附加质量力和 BBH。对足够小的颗粒忽略 Faxén 修正后，MRG 的无量纲形式为

$$
\frac{\mathrm d\boldsymbol x_p}{\mathrm dt}
=\boldsymbol w_s+\boldsymbol u(\boldsymbol x_p),
\tag{1a}
$$

$$
\frac{\mathrm d\boldsymbol w_s(t)}{\mathrm dt}
=-\alpha\boldsymbol w_s
-\gamma\int_0^t\frac{1}{\sqrt{\pi(t-\tau)}}
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau
+\boldsymbol N\!\left(\boldsymbol u(\boldsymbol x_p),\boldsymbol w_s\right),
\tag{1b}
$$

其中

$$
\alpha\equiv\frac{1}{RS},\qquad
\gamma\equiv\sqrt{\frac{3}{R^2S}},\qquad
S\equiv\frac{1}{3}\frac{a^2/\nu}{T},\qquad
R\equiv\frac{1+2\beta}{3},
$$

且

$$
\boldsymbol N\!\left(\boldsymbol u(\boldsymbol x_p),\boldsymbol w_s\right)
=\left(\frac{1}{R}-1\right)
\left.\frac{D\boldsymbol u}{Dt}\right|_{\boldsymbol x_p}
-\left.\boldsymbol w_s\cdot\boldsymbol\nabla\boldsymbol u\right|_{\boldsymbol x_p}.
$$

> **【说明】**$\boldsymbol x_p(t)$ 为颗粒瞬时位置；$\boldsymbol w_s(t)=\dot{\boldsymbol x}_p-\boldsymbol u(\boldsymbol x_p)$ 为滑移速度；$\boldsymbol u(\boldsymbol x,t)$ 为非均匀未扰动流速；$\beta$ 为颗粒与流体的密度比；$T$ 为所选流动时间尺度；$S$ 是颗粒黏性响应时间与 $T$ 构成的 Stokes 数；$R$ 是密度比参数；$\alpha$ 控制 Stokes 阻力，$\gamma$ 控制历史力；$\boldsymbol N$ 汇集压力梯度与附加质量相关贡献。式（1b）的卷积积分即采用 Basset 核 $K_B(t)=1/\sqrt{\pi t}$ 的标准历史力。

式（1b）中各竞争作用力的相对重要性取决于颗粒—流体密度比参数 $R$、局部颗粒响应时间与流动时间之比 $S$，以及 Reynolds 数。传统的密度比论证认为：对边际重颗粒（$R\sim1$），BBH 与 Stokes 阻力同等重要；对远重于流体的颗粒（$R\to\infty$），BBH 可以忽略。不过，后一结论仅对点颗粒成立。对式（1b）的尺度分析表明，对有限尺寸颗粒，Stokes 阻力与 BBH 的相对强度并不依赖密度比，而取决于颗粒响应时间与流动时间之比 $S$ [[#^ref-22|22]],[[#^ref-30|30]],[[#^ref-31|31]]。颗粒 Reynolds 数则会通过改变核函数的形式，从根本上改变历史力的强度。

为便于讨论历史核的各种形式及其数值方法，可将历史力写为一般形式

$$
\boldsymbol F_h(t)
=-\int_0^t K\!\left(t-\tau,\boldsymbol w_s\right)
\frac{\mathrm d\boldsymbol w_s}{\mathrm d\tau}\,\mathrm d\tau,
\tag{2}
$$

其中 $K$ 为一般历史核；对于 BBH，$K$ 退化为 $K_B(t)=1/\sqrt{\pi t}$。

> **【说明】**$\boldsymbol F_h$ 为历史力；$K$ 决定过去各时刻对当前作用力的权重；$t-\tau$ 是记忆年龄；$\mathrm d\boldsymbol w_s/\mathrm d\tau$ 为过去的滑移加速度。Basset 核按 $(t-\tau)^{-1/2}$ 缓慢衰减，因此“久远历史”的影响不会像指数核那样迅速消失，同时核在 $\tau\to t$ 时具有弱奇异性。

## 2 理论进展：历史核

理论研究表明，历史核的函数形式会随基础物理机制而偏离标准形式。在高 Reynolds 数以及颗粒周围尾迹初始加速或减速等不同条件下，研究者已推导出多种变体，相关综述见文献 [[#^ref-32|32]]–[[#^ref-34|34]]。本文选择性讨论在蠕动流极限 $Re_s,Re_p\ll1$ 内促使标准核发生偏离的两个物理因素：其一是刚性颗粒在晚时间出现的平流或对流惯性动力学；其二是颗粒—流体界面的滑移程度。

### 2.1 刚性颗粒晚时间平流／对流惯性效应的出现

在蠕动流极限下，惯性时间尺度较慢，并与更快的黏性扩散时间尺度 $\tau_\nu\approx a^2/\nu$ 明显分离。然而，颗粒在流体中加速时会经历一系列时间尺度，其中惯性效应可能变得重要。因此，需要以 Strouhal 数 $Sl=\tau_i/\tau^*$ 衡量所关注时间尺度 $\tau^*$ 相对于惯性时间尺度 $\tau_i$ 的大小。通常，颗粒对流时间 $a/W_s$（记作 $\tau_p$）或流动梯度的倒数 $1/s$（记作 $\tau_s$）可作为惯性时间尺度，而 $\tau^*$ 则取决于具体研究区间。

对非均匀未扰动流，在随颗粒平移的参考系中，扰动场的无量纲 Navier–Stokes 方程为

$$
Re_iSl\,\frac{\partial\boldsymbol w_d}{\partial t}
+Re_s(\boldsymbol w_d\cdot\boldsymbol\nabla)\boldsymbol u
+Re_p\left[(\boldsymbol w_{ud}\cdot\boldsymbol\nabla)\boldsymbol w_d
+(\boldsymbol w_d\cdot\boldsymbol\nabla)\boldsymbol w_d\right]
=-\boldsymbol\nabla p_d+\nabla^2\boldsymbol w_d.
\tag{3}
$$

这里，$\boldsymbol w_{ud}(\boldsymbol r)=\boldsymbol u(\boldsymbol x)-\dot{\boldsymbol x}_p(t)$ 是在移动参考系中观察到的已知未扰动场；$Re_i=a^2/(\nu\tau_i)$，根据适用的惯性时间尺度取 $Re_p$ 或 $Re_s$；空间梯度相对于瞬时坐标 $\boldsymbol r=\boldsymbol x-\boldsymbol x_p(t)$ 计算。式（3）中距离以 $a$ 标度化，显式出现的时间以 $\tau^*$ 标度化，速度以 $W_s$ 标度化，未扰动场梯度以 $s$ 标度化。Strouhal 数表示非定常惯性项 $|\partial\boldsymbol w_d/\partial t|$ 相对于剪切诱导惯性项和式（3）括号内对流项的重要程度。

**早时间扩散动力学。** 对从静止开始、置于均匀时变流 $\boldsymbol u=\boldsymbol u(t)$ 中的颗粒，Boussinesq [[#^ref-35|35]] 和 Basset [[#^ref-36|36]] 证明，在 $\tau^*\sim\tau_\nu$ 的早时间，主导动力学由非定常 Stokes 方程控制，因而得到带 Basset 核的历史力。Maxey 和 Riley [[#^ref-1|1]] 以及 Gatignol [[#^ref-2|2]] 对非均匀流 $\boldsymbol u=\boldsymbol u(\boldsymbol x,t)$ 推导出了相同的历史核。因此，对应早时间与 MRG 模型的 $Re_iSl\sim O(1)$，归一化历史力为

$$
\boldsymbol F_h(t)
=-6\pi\int_0^t\frac{1}{\sqrt{\pi(t-\tau)}}
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau
\equiv-6\pi\boldsymbol F_{BBH}(t),
\tag{4}
$$

其中时间以 $\tau^*=\tau_\nu$ 标度化。

**晚时间平流／对流动力学。** 当晚时间满足 $\tau^*\sim\tau_i$ 时，惯性效应通过对流或剪切诱导平流出现，分别对应以下两个极限。

#### （i）Oseen 极限

其条件为 $Re_s^{1/2}\ll Re_p<1$，此时 $\tau^*\sim\nu/W_s^2\gg\tau_\nu$，且 $Sl\sim O(Re_p)$。Mei 和 Adrian [[#^ref-37|37]]、Lovalenti 和 Brady [[#^ref-38|38]] 证明，此时会偏离 MRG 模型，历史核比标准核衰减得更快。这源于扰动场形成空间上可区分的内区和外区，类似经典稳态 Oseen 问题。在以 Oseen 距离 $r\sim Re_p^{-1}$ 为特征的外区，对流惯性项与黏性项同阶；在靠近颗粒表面的 $r\sim1$ 内区，则逐渐形成稳态 Stokes 流。这意味着在足够长时间后，颗粒表面产生的涡量会逸出至 Oseen 距离，而输运的主要方式转为对流。

Mei 和 Adrian [[#^ref-37|37]] 提出了一个能够统一捕捉早、晚时间行为的半经验历史力表达式：

$$
\boldsymbol F_h(t)\approx-6\pi Re_p\int_0^t
\left\{[\pi(t-\tau)]^{1/4}+f(Re_p,t)(t-\tau)\right\}^{-2}
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau,
\tag{5}
$$

其中时间以 $\tau^*=\nu/W_s^2$ 标度化，$f(Re_p,t)$ 是已有明确定义的函数。由于它显式依赖当前时间，该表达式不再具有严格的时间卷积形式；但在短时间 $t\to0$ 时，其核退化为标准核。

#### （ii）Saffman 极限

其条件为 $Re_p\ll Re_s^{1/2}<1$。Candelier 等 [[#^ref-39|39]],[[#^ref-40|40]] 引入线性非均匀流

$$
\boldsymbol u(\boldsymbol x,t)=\boldsymbol U(t)+\mathsf A\cdot\boldsymbol x,
$$

研究剪切诱导惯性对颗粒受力的影响。这里，$\mathsf A$ 是与时间和空间均无关的速度梯度张量，其特征应变率为 $s$。当 $\tau^*\sim1/s$ 且 $Sl=O(1)$ 时，在 $r\sim Re_s^{-1/2}$ 处形成外区。以小参数 $Re_s^{1/2}$ 展开至二阶，历史力为

$$
\boldsymbol F_h(t)=-6\pi\left[
Re_s^{1/2}\int_0^t\mathsf K(t-\tau)\cdot
\frac{\mathrm d\boldsymbol w_s}{\mathrm d\tau}\,\mathrm d\tau
+Re_s\int_0^t\mathsf K(t-\tau)\cdot
\frac{\mathrm d}{\mathrm d\tau}
\left(\int_0^\tau\mathsf K(\tau-\sigma)\cdot
\frac{\mathrm d\boldsymbol w_s}{\mathrm d\sigma}\,\mathrm d\sigma\right)\mathrm d\tau
\right].
\tag{6}
$$

其中时间以 $\tau^*=1/s$ 标度化，$\mathsf K$ 是依赖流动的核张量。早时间时该张量成为对角张量，各对角元恢复标准核。有限时间修正会使对角元（阻力）和非对角元（剪切诱导升力）逐渐发展，具体形式依赖流动。

**图 1** 将 Saffman 极限和 Oseen 极限分别示意，但在实际流动中，两者可能以复杂方式组合出现。

![Jaganathan2023 Basset历史力适用性与数值进展_page4_fig1.png](/vault/papers/jaganathan2023basset/images/Jaganathan2023%20Basset%E5%8E%86%E5%8F%B2%E5%8A%9B%E9%80%82%E7%94%A8%E6%80%A7%E4%B8%8E%E6%95%B0%E5%80%BC%E8%BF%9B%E5%B1%95_page4_fig1.png)

**图 1　Oseen 极限与 Saffman 极限中主导物理的时空图景。** （i）Oseen 极限：$Re_s^{1/2}\ll Re_p<1$；（ii）Saffman 极限：$Re_p\ll Re_s^{1/2}<1$。图中三元组 $(\circ,\circ,\circ)$ 依次表示非定常惯性 $|\partial\boldsymbol w_d/\partial t|$、剪切平流惯性 $|\boldsymbol w_d\cdot\nabla\boldsymbol u|$ 和滑移对流惯性 $|\boldsymbol w_d\cdot\nabla\boldsymbol w_d|$ 相对于黏性项 $|\nabla^2\boldsymbol w_d|\sim|\nabla p_d|$ 的强弱；星号表示有量纲量。在两个极限下，晚时间均会形成空间上不同的“内区”和“外区”，标准核因此分别偏离为式（5）和式（6）。短时间时，扩散型非定常 Stokes 方程在整个空间统一地主导动力学，因而仍产生标准 Basset 核。示意构思参考 Bentwich 和 Miloh [[#^ref-60|60]] 以及 Sano [[#^ref-59|59]]。

### 2.2 滑移界面颗粒的核

“滑移”一词通常表示颗粒速度与颗粒位置处未扰动流体速度之差。这只是一种术语；事实上，刚性颗粒阻力的经典推导在颗粒—流体界面施加的是无滑移边界条件。当疏水物体等界面允许一定的真实滑移时，会产生修正的历史力。Gatignol [[#^ref-41|41]] 给出的历史核为

$$
K(t)=\frac{1}{\delta}
\exp\!\left(\frac{t\nu}{a^2\delta^2}\right)
\operatorname{erfc}\!\left(\frac{\sqrt{t\nu}}{a\delta}\right),
$$

其中 $\delta$ 为滑移参数；当 $\delta\to0$ 时恢复无滑移条件下的标准核。Premlata 和 Wei [[#^ref-42|42]] 也研究了类似非 Basset 型核对部分滑移颗粒的影响。

Yang 和 Leal [[#^ref-43|43]]、Galindo 和 Gerbeth [[#^ref-44|44]] 推导了静止流体中加速球形液滴所受的流体动力，其中液滴黏度为 $\mu_d$，外部流体黏度为 $\mu$。液滴的修正历史核具有

$$
K_B(t;\mu_d/\mu)+K_{new}(t;\mu_d/\mu)
$$

的形式，$K_{new}$ 的显著特征是随时间非单调变化。标准核在初始时刻奇异，而新核始终有限；另一方面，两者具有相似的长时间行为。当 $\mu_d/\mu\to0$、对应保持形状的“气泡”时，核退化为 Gatignol [[#^ref-41|41]] 中 $\delta=1/3$ 的形式。文献 [[#^ref-45|45]],[[#^ref-46|46]] 的实验为上述滑移颗粒（液滴与气泡）历史核在短时间内的有效性提供了证据。

## 3 数值方法进展

前面的讨论表明，历史力的形式与基础物理机制紧密相关；不过它总能写成式（2）的一般形式，而且对刚性颗粒在 $t\to0$ 时总会呈现式（4）的奇异 BBH 形式。本节以 BBH 为模型形式，讨论其特殊性以及求解式（1b）的数值方法进展。这里介绍的多数方法可以推广到其他历史核，尤其是 $K_B(t)+K_{new}(t)$ 型核，其中 $K_{new}$ 是无奇异性的良态函数。然而，构造能够处理各种奇异核的通用方法，仍是活跃的研究方向。

### 3.1 标准 Basset 核

对任意初始滑移速度，时刻 $t$ 的修正 BBH 为

$$
\frac{\boldsymbol w_s(0)}{\sqrt{\pi t}}
+\int_0^t\frac{1}{\sqrt{\pi(t-\tau)}}
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau.
\tag{7}
$$

若颗粒初始滑移速度非零，第一项会在初始时刻产生奇异性。数值实现中常通过强行设置不符合物理的零初始滑移速度来回避此项。然而，由于惯性颗粒需要有限时间响应流动，一般应当允许非零初始滑移速度。采用等价表示 [[#^ref-47|47]]，修正 BBH 可写成 Riemann–Liouville 半阶导数：

$$
\frac{\mathrm d}{\mathrm dt}
\int_0^t\frac{\boldsymbol w_s(\tau)}{\sqrt{\pi(t-\tau)}}\,\mathrm d\tau
\equiv\frac{\mathrm d^{1/2}\boldsymbol w_s(t)}{\mathrm dt^{1/2}}.
\tag{8}
$$

> **【说明】**$\boldsymbol w_s(0)/\sqrt{\pi t}$ 是非零初始滑移带来的初始奇异项；积分中的 $(t-\tau)^{-1/2}$ 是长记忆核；右端 $\mathrm d^{1/2}/\mathrm dt^{1/2}$ 表示 Riemann–Liouville 半阶导数。式（7）与式（8）等价，均表明 BBH 对时间是非局部的：当前状态因核在 $\tau=t$ 处的奇异性具有最“鲜明”的记忆，而过去状态的影响仅随经过时间作代数衰减。

半阶导数联系是下一节数值格式的基础。由于核的形式和时间非局部性，MRG 并不是通常意义上的动力系统 [[#^ref-5|5]],[[#^ref-6|6]]：仅给出时刻 $t$ 的颗粒位置和速度，不足以唯一确定系统在位置—速度空间中的后续路径。因此不能直接使用标准常微分方程积分器，而且每个时间步都无法避免历史积分的计算。计算历史积分意味着：一方面必须存储全部过去状态；另一方面必须执行卷积运算。随着系统向前演化，二者的开销都会增加。若离散时刻为 $t_N=N\Delta t$，则运算量随时间步数按 $O(N^2)$ 增长，存储量按 $O(N)$ 增长。这种不断增加的成本，正是很多研究不论是否合理都直接忽略式（1b）历史力、从而得到普通动力系统的原因。下面介绍的方案则保留历史效应。

### 3.2 数值方法概览

依据解决上述计算困难的总体策略，可将数值方法分为以下几类。Moreno-Casas 和 Bombardelli [[#^ref-48|48]] 的较早综述可作为补充；本文还纳入了其后发展的方法。

#### 3.2.1 全历史求积

Daitche [[#^ref-47|47]] 提出了一种以任意高阶精度计算 BBH 积分的一般方案。利用式（8），MRG 的积分形式可写为

$$
\begin{aligned}
\boldsymbol w_s(t_{n+1})={}&\boldsymbol w_s(t_n)
+\left[\int_0^{t_{n+1}}K_B(t_{n+1}-\tau)\boldsymbol w_s(\tau)\,\mathrm d\tau
-\int_0^{t_n}K_B(t_n-\tau)\boldsymbol w_s(\tau)\,\mathrm d\tau\right]\\
&+\int_{t_n}^{t_{n+1}}
\left[-\alpha\boldsymbol w_s(\tau)+\boldsymbol N(\boldsymbol w_s(\tau))\right]\mathrm d\tau.
\end{aligned}
\tag{9}
$$

求积程序通常对被积函数作多项式插值，并要求在积分端点计算被积函数。Daitche [[#^ref-47|47]] 只对滑移速度采用 Lagrange 多项式插值，而保持核及其奇异性不变，随后精确计算所得积分。插值多项式次数决定格式的精度阶。求积可写为

$$
\begin{aligned}
\int_0^{t_n}K_B(t_n-\tau)\boldsymbol w_s(\tau)\,\mathrm d\tau
&=\sum_{m=1}^{n}\int_{t_{m-1}}^{t_m}
K_B(t_n-\tau)\boldsymbol w_s(\tau)\,\mathrm d\tau\\
&\approx\sqrt{\Delta t}\sum_{m=1}^{n}\mu_m^n
\boldsymbol w_s(t_{n-m}).
\end{aligned}
\tag{10}
$$

其中 $\{\mu_m^n\}$ 是取决于具体格式和时间的权重，可预先计算。Daitche [[#^ref-47|47]] 显式给出了精度为 $O(\Delta t)$、$O(\Delta t^2)$ 和 $O(\Delta t^3)$ 的格式。由于求积仍需保存过去的滑移速度，存储量与运算量会继续增长；但更高阶格式基本不引入额外成本。

另一类针对分数阶微分方程设计的全历史求积格式见 Garrappa 和 Popolizio [[#^ref-49|49]]、Garrappa [[#^ref-50|50]]。这些方法类似 Cox 和 Matthews [[#^ref-51|51]] 的指数时间差分积分器，但针对分数阶导数作了调整。

#### 3.2.2 基于时间窗的方法

这类方法将式（7）的积分分成“久远历史”和“近期历史”两部分。其动机是在当前时刻附近准确处理奇异性，同时近似久远历史中的核，以降低运算成本。一般构造为

$$
\begin{aligned}
\boldsymbol F_{BBH}(t_n)
&\equiv\int_0^{t_n}K_B(t_n-\tau)
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau\\
&\approx\boldsymbol F_{tail}(t_n)+\boldsymbol F_{win}(t_n),
\end{aligned}
\tag{11}
$$

其中

$$
\boldsymbol F_{tail}(t_n)=
\int_0^{t_n-t_{win}}K_{tail}(t_n-\tau)
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau,
$$

$$
\boldsymbol F_{win}(t_n)=
\int_{t_n-t_{win}}^{t_n}K_{win}(t_n-\tau)
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau.
\tag{12}
$$

> **【说明】**$t_{win}=M\Delta t$ 是近期历史窗宽，$M$ 是窗内时间步数；$K_{win}$ 用于近期窗口，通常保留真实 Basset 核以准确处理当前时刻奇异性；$K_{tail}$ 用于久远历史，可截断或以快速递推核近似。该分割不是普遍可忽略长记忆的证明，窗宽及尾核近似必须按问题和误差要求选择。

当前时刻的奇异性总位于 $[t_n-t_{win},t_n]$ 内，因此通常在这个窗口保留核的原形式，即令 $K_{win}=K_B$，再采用类似 Daitche [[#^ref-47|47]] 的求积格式。例如，Brush 等 [[#^ref-52|52]] 假设滑移加速度为常数，van Hinsberg 等 [[#^ref-53|53]] 对滑移加速度采用线性插值。另一种做法是不用求积构造：Bombardelli 等 [[#^ref-54|54]] 使用 Riemann–Liouville 半阶导数的级数表示近似近期窗口中的积分。

在尾部窗口 $[0,t_n-t_{win}]$ 内，人们寻求快速收敛的近似核。Dorgan 和 Loth [[#^ref-55|55]]、Bombardelli 等 [[#^ref-54|54]] 完全忽略尾部，相当于令 $K_{tail}=0$，从而截断历史积分。另一类是指数近似方法，例如 van Hinsberg 等 [[#^ref-53|53]] 用若干衰减指数之和近似尾部区间内的 $K_B$。对方法相关的正常数 $\{a_i,t_i\}$ 以及已知函数 $\alpha(t_i)$、$\beta(t_i)$，尾部积分为

$$
\begin{aligned}
\boldsymbol F_{tail}(t_n)
&=\sum_{i=1}^{m}\boldsymbol F_i(t_n)\\
&=\sum_{i=1}^{m}\int_0^{t_n-t_{win}}
 a_i\alpha(t_i)e^{-\beta(t_i)(t_n-\tau)}
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau.
\end{aligned}
\tag{13}
$$

特别地，每个指数分量可递推为

$$
\begin{aligned}
\boldsymbol F_i(t_n)={}&e^{-\beta(t_i)\Delta t}\boldsymbol F_i(t_n-\Delta t)\\
&+a_i\alpha(t_i)\int_{t_n-t_{win}-\Delta t}^{t_n-t_{win}}
 e^{-\beta(t_i)(t_n-\tau)}
\frac{\mathrm d\boldsymbol w_s(\tau)}{\mathrm d\tau}\,\mathrm d\tau.
\end{aligned}
\tag{14}
$$

这种尾积分处理之所以能够递推，正是因为采用了指数形式的核近似。这也说明 $\boldsymbol F_i(t)$ 可视为满足由滑移加速度驱动的线性方程的动力学变量。Parmar 等 [[#^ref-56|56]] 基本沿用这一思想，为每个近似力 $\boldsymbol F_i(t)$ 建立微分方程。小的 $t_{win}$ 可显著缩短求积区间；指数近似依照 Beylkin 和 Monzón [[#^ref-57|57]] 构造，除此之外其方法与上述方案相似。

对基于时间窗的方法，$t_{win}$ 必须慎重选择，判据通常依赖具体问题。Bombardelli 等 [[#^ref-54|54]] 针对其物理系统，根据颗粒状态相关性变弱的时间确定 $t_{win}$。van Hinsberg 等 [[#^ref-53|53]] 和 Parmar 等 [[#^ref-56|56]] 则通过最小化一个误差型指标确定最优 $t_{win}$；Casas 等 [[#^ref-58|58]] 进一步改进了 van Hinsberg 等 [[#^ref-53|53]] 方法中的优化过程。

#### 3.2.3 偏微分方程表述

Prasath 等 [[#^ref-6|6]] 提出了一条不同路径：完整的 MRG 方程可以写成半无限区间上一维扩散方程的动态边界条件。此类系统已有丰富理论并可求解。其关键事实是，扩散方程的 Dirichlet–Neumann 算子在相差一个符号的意义下就是 Riemann–Liouville 半阶导数。时间窗方法暗示或构造的是 MRG 的近似动力系统，而 Prasath 等 [[#^ref-6|6]] 给出了一个时间局部的精确重构。

定义伪空间坐标 $\zeta>0$ 上的扩散量 $\boldsymbol q(\zeta,t)$，并令滑移速度满足 $\boldsymbol q(0,t)\equiv\boldsymbol w_s(t)$，则系统为

$$
\boldsymbol q_t=\boldsymbol q_{\zeta\zeta},
\tag{15a}
$$

$$
\boldsymbol q(\zeta>0,0)=0,
\tag{15b}
$$

$$
\boldsymbol q_t(0,t)+\alpha\boldsymbol q(0,t)-\gamma\boldsymbol q_\zeta(0,t)
=\boldsymbol N\!\left(\boldsymbol q(0,t),\boldsymbol u(\boldsymbol x_p(t))\right),
\tag{15c}
$$

$$
\lim_{t\to0}\boldsymbol q(0,t)=\boldsymbol w_s(0).
\tag{15d}
$$

> **【说明】**$\zeta$ 是为局部化记忆项而引入的伪空间坐标，并非实际物理空间；$\boldsymbol q$ 满足一维扩散方程；边界值 $\boldsymbol q(0,t)$ 就是滑移速度；边界通量 $\boldsymbol q_\zeta(0,t)$ 表示 BBH 项；$\alpha$、$\gamma$ 与式（1）相同；式（15c）表明 MRG 恰好表现为广义 Robin 动态边界条件。该变换没有近似 Basset 核，而是把时间非局部性转换为空间扩散问题。

利用这一重构，可在已知 $\boldsymbol q(0,t_n)$ 的条件下求 $t_n<t\le t_{n+1}$ 的 $\boldsymbol q(0,t)$，同时引入新的动力学量“历史函数”$\boldsymbol H(k,t)$：

$$
\begin{aligned}
-\frac{\pi}{2}\boldsymbol q(0,t)={}&
\int_0^\infty e^{-k^2(t-t_n)}\operatorname{Im}[k\boldsymbol H(k,t_n)]\,\mathrm dk\\
&+\int_0^{t-t_n}\boldsymbol N\!\left(\boldsymbol q(0,t_n+\tau)\right)
\left\{\int_0^\infty\operatorname{Im}\left[
\frac{k e^{-k^2(t-t_n-\tau)}}{ik\gamma-k^2+\alpha}
\right]\mathrm dk\right\}\mathrm d\tau,
\end{aligned}
\tag{16a}
$$

$$
\begin{aligned}
\boldsymbol H(k,t_{n+1})={}&e^{-k^2\Delta t}\boldsymbol H(k,t_n)\\
&-\int_0^{\Delta t}e^{-k^2(\Delta t-\tau)}
\frac{\boldsymbol q(0,t_n+\tau)+\boldsymbol N(\boldsymbol q(0,t_n+\tau))}
{ik\gamma-k^2+\alpha}\,\mathrm d\tau.
\end{aligned}
\tag{16b}
$$

在 $t=0$ 时，历史函数可解析给出；当 $t_n>0$ 时，用 Chebyshev 多项式表示 $\boldsymbol H(k,t_n)$，并假设时间区间 $[t_n,t_{n+1}]$ 内的滑移速度 $\boldsymbol q(0,t)$ 也具有 Chebyshev 展开。给定 $\boldsymbol H(k,t_n)$ 后，Prasath 等 [[#^ref-6|6]] 使用 Newton 方法求解式（16a）中 $\boldsymbol q(0,t)$ 的 Chebyshev 系数，再通过式（16b）更新历史，以求下一时间步的滑移速度。该方法的突出优点是不近似历史核；而且把 $\boldsymbol H(k,t)$ 作为动力学变量后，运算成本、存储需求以及重启模拟所需成本都不再随已模拟时间增长。

总之，数值方法的选择取决于可用计算资源和所需精度。**表 1** 按计算开销如何随模拟时间（约为 $N$ 个时间步）增长比较各方案。实际开销还乘有依赖具体方法的系数，因此不同方法之间存在随模拟时长变化的盈亏平衡点。简要而言：

- 对短时模拟，历史存储尚少，全历史求积具有可扩展的精度，且短时间内成本不高，是合理选择；
- 对快速衰减的核，例如式（5），基于时间窗的方法能有效减轻计算负担；
- 对长时间、多颗粒模拟，尤其是事先难以判断动力学特征的湍流颗粒问题，PDE 重构能够在计算成本不随已模拟时间增长的前提下保证精度。

**表 1　不同 BBH 数值方法的计算需求与精度。** $N\Delta t$ 为模拟时长，$M=t_{win}/\Delta t$ 为预先固定的近期窗口内时间步数。这里 $O(\Delta t^p)$ 表示格式局部误差按 $O(\Delta t^{p+1})$ 标度。

| 方法 | 存储需求 | 运算成本 | 已有格式精度 |
| --- | --- | --- | --- |
| 全历史求积 | $O(N)$ | $O(N^2)$ | $O(\Delta t)$、$O(\Delta t^2)$、$O(\Delta t^3)$ |
| 时间窗方法（窗口 $=M\Delta t$） | 当 $N\lt M$ 时为 $O(N)$；当 $N\ge M$ 时为 $O(M)$ | 当 $N\lt M$ 时为 $O(N^2)$；当 $N\ge M$ 时为 $O(M^2)+O(N-M)$ | $O(\Delta t^{1/2})$、$O(\Delta t)$ |
| PDE 表述 | 常数 | $O(N)$ | 谱精度 |

## 4 总结与未来方向

非均匀流中惯性颗粒无处不在，因此必须发展能够准确获得其动力学的方法。本文重点回顾的解析与数值研究表明：为描述实验观察到的瞬态动力学，在模型中加入历史力十分重要；然而，许多统计性质却常常不受历史力影响，这一点仍需进一步理解。

模拟大量含历史力颗粒的计算障碍，已被第 3.2 节所述数值策略逐步缩小，从而为大规模系统中历史效应的数值探索打开了道路。不过，对于一般多尺度流动中历史力的作用及其函数形式，目前仍缺乏共识，并由此产生若干开放问题。下面列出两个很有前景的方向。

- **湍流中的历史力。** 针对简单流动中单颗粒的现有理论 [[#^ref-37|37]]–[[#^ref-40|40]],[[#^ref-59|59]] 已表明，随着多个时间尺度上性质根本不同的物理机制出现，历史力会改变形式。这促使人们研究：惯性颗粒在湍流中采样随时间和空间变化的结构时，究竟受到何种历史力。
- **颗粒间流体动力相互作用与碰撞核。** BBH（以及 MRG）是针对孤立颗粒推导的，因而其推广只适用于稀悬浮体系。颗粒相互接近时历史力采取什么形式，尚未得到探索。颗粒间相互作用是否产生屏蔽效应并压过历史效应？颗粒碰撞或液滴合并时，各自历史如何交换或组合？这些问题的答案将为准确构造碰撞核提供依据。

无论最终证明历史力及其效应重要与否，对这些问题的研究都很可能产生有价值的新认识。

## 作者贡献

所有列名作者均对本研究作出了实质性、直接且智力层面的贡献，并批准论文发表。

## 经费

本研究得到印度政府原子能部项目 RTI4001 的支持。

## 致谢

作者感谢 ICTS-TIFR 的 Saumav Kapoor 提供意见。

## 利益冲突声明

作者声明，本研究未在任何可能被解释为潜在利益冲突的商业或财务关系下开展。

## 出版者说明

本文表达的全部主张仅代表作者本人，并不必然代表其所属机构、出版者、编辑或审稿人的观点。本文可能评价的任何产品或其制造商可能作出的任何声明，出版者均不作保证或背书。

## 参考文献

<!--REFS_AUTO-->
> 🤖 由 build_refs.py 自动生成（条目保持原文、不翻译）：共 60 条，带 DOI 链接 45 条，📥 库内已入库 0 篇。

- **[1]** Maxey MR, Riley JJ. Equation of motion for a small rigid sphere in a nonuniform ﬂow. Phys Fluids (1983) 26:883–9. doi:10.1063/1.864230 ｜ [🔗 DOI](https://doi.org/10.1063/1.864230) ^ref-1
- **[2]** Gatignol R. The Faxén formulae for a rigid particle in an unsteady non-uniform Stokes ﬂow. J Mec Theor Appl (1983) 2:241–82. ^ref-2
- **[3]** Basset AB. (1910). On the descent of a sphere in a viscous liquid, 41 ^ref-3
- **[4]** Belmonte A, Jacobsen J, Jayaraman A. Monotone solutions of a nonautonomous differential equation for a sedimenting sphere. Electron J Diff Eqns (2001) 2001:1–17. ^ref-4
- **[5]** Farazmand M, Haller G. The Maxey–Riley equation: Existence, uniqueness and regularity of solutions. Nonlinear Anal Real World Appl (2015) 22:98–106. doi:10.1016/ j.nonrwa.2014.08.002 ^ref-5
- **[6]** Prasath SG, Vasan V, Govindarajan R. Accurate solution method for the Maxey–Riley equation, and the effects of Basset history. J Fluid Mech (2019) 868: 428–60. doi:10.1017/jfm.2019.194 ｜ [🔗 DOI](https://doi.org/10.1017/jfm.2019.194) ^ref-6
- **[7]** Mordant N, Pinton J. Velocity measurement of a settling sphere. Eur Phys J B (2000) 18:343–52. doi:10.1007/pl00011074 ｜ [🔗 DOI](https://doi.org/10.1007/pl00011074) ^ref-7
- **[8]** Rahman A. Correlations in the motion of atoms in liquid Argon. Phys Rev (1964) 136:A405–11. doi:10.1103/physrev.136.a405 ｜ [🔗 DOI](https://doi.org/10.1103/physrev.136.a405) ^ref-8
- **[9]** Alder BJ, Wainwright TE. Decay of the velocity autocorrelation function. Phys Rev A (1970) 1:18–21. doi:10.1103/physreva.1.18 ｜ [🔗 DOI](https://doi.org/10.1103/physreva.1.18) ^ref-9
- **[10]** Zwanzig R, Bixon M. Hydrodynamic theory of the velocity correlation function. Phys Rev A (1970) 2:2005–12. doi:10.1103/physreva.2.2005 ｜ [🔗 DOI](https://doi.org/10.1103/physreva.2.2005) ^ref-10
- **[11]** Widom A. Velocity ﬂuctuations of a hard-core Brownian particle. Phys Rev A (1971) 3:1394–6. doi:10.1103/physreva.3.1394 ｜ [🔗 DOI](https://doi.org/10.1103/physreva.3.1394) ^ref-11
- **[12]** Hinch EJ. Application of the Langevin equation to ﬂuid suspensions. J Fluid Mech (1975) 72:499–511. doi:10.1017/s0022112075003102 ｜ [🔗 DOI](https://doi.org/10.1017/s0022112075003102) ^ref-12
- **[13]** Clercx HJH, Schram PPJM. Brownian particles in shear ﬂow and harmonic potentials: A study of long-time tails. Phys Rev A (1992) 46:1942–50. doi:10.1103/ physreva.46.1942 ^ref-13
- **[14]** Druzhinin O, Ostrovsky L. The inﬂuence of Basset force on particle dynamics in two-dimensional ﬂows. Physica D (1994) 76:34–43. doi:10.1016/0167-2789(94)90248-8 ｜ [🔗 DOI](https://doi.org/10.1016/0167-2789%2894%2990248-8) ^ref-14
- **[15]** Candelier F, Angilella JR, Souhar M. On the effect of the Boussinesq–Basset force on the radial migration of a Stokes particle in a vortex. Phys Fluids (2004) 16:1765–76. doi:10.1063/1.1689970 ｜ [🔗 DOI](https://doi.org/10.1063/1.1689970) ^ref-15
- **[16]** Sapsis TP, Ouellette NT, Gollub JP, Haller G. (2011). Neutrally buoyant particle dynamics in ﬂuid ﬂows: Comparison of experiments with Lagrangian stochastic models. Phys Fluids 23, 093304. doi:10.1063/1.3632100 ｜ [🔗 DOI](https://doi.org/10.1063/1.3632100) ^ref-16
- **[17]** Ouellette NT, O’Malley PJJ, Gollub JP. Transport of ﬁnite-sized particles in chaotic ﬂow. Phys Rev Lett (2008) 101:174504. doi:10.1103/physrevlett.101.174504 ｜ [🔗 DOI](https://doi.org/10.1103/physrevlett.101.174504) ^ref-17
- **[18]** Mei R, Adrian RJ, Hanratty TJ. Particle dispersion in isotropic turbulence under Stokes drag and Basset force with gravitational settling. J Fluid Mech (1991) 225:481–95. doi:10.1017/s0022112091002136 ｜ [🔗 DOI](https://doi.org/10.1017/s0022112091002136) ^ref-18
- **[19]** Elghobashi S, Truesdell GC. Direct simulation of particle dispersion in a decaying isotropic turbulence. (1992) 242:655–700. s0022112092002532 ^ref-19
- **[20]** Armenio V, Fiorotto V. The importance of the forces acting on particles in turbulent ﬂows. Phys Fluids (2001) 13:2437–40. doi:10.1063/1.1385390 ｜ [🔗 DOI](https://doi.org/10.1063/1.1385390) ^ref-20
- **[21]** van Aartrijk M, Clercx HJH. Vertical dispersion of light inertial particles in stably stratiﬁed turbulence: The inﬂuence of the Basset force. Phys Fluids (2010) 22:013301. doi:10.1063/1.3291678 ｜ [🔗 DOI](https://doi.org/10.1063/1.3291678) ^ref-21
- **[22]** Daitche A, Tél T. Memory effects are relevant for chaotic advection of inertial particles. Phys Rev Lett (2011) 107:244501. doi:10.1103/physrevlett.107.244501 ｜ [🔗 DOI](https://doi.org/10.1103/physrevlett.107.244501) ^ref-22
- **[23]** Calzavarini E, Volk R, Lévêque E, Pinton J-F, Toschi F. Impact of trailing wake drag on the statistical properties and dynamics of ﬁnite-sized particle in turbulence. Physica D (2012) 241:237–44. doi:10.1016/j.physd.2011.06.004 ｜ [🔗 DOI](https://doi.org/10.1016/j.physd.2011.06.004) ^ref-23
- **[24]** Guseva K, Feudel U, Tél T. Inﬂuence of the history force on inertial particle advection: Gravitational effects and horizontal diffusion. Phys Rev E 88 (2013) 88: 042909. doi:10.1103/physreve.88.042909 ｜ [🔗 DOI](https://doi.org/10.1103/physreve.88.042909) ^ref-24
- **[25]** Olivieri S, Picano F, Sardina G, Iudicone D, Brandt L. The effect of the Basset history force on particle clustering in homogeneous and isotropic turbulence. Phys Fluids 26 (2014) 26:041704. doi:10.1063/1.4871480041704 ｜ [🔗 DOI](https://doi.org/10.1063/1.4871480041704) ^ref-25
- **[26]** Daitche A. On the role of the history force for inertial particles in turbulence. J Fluid Mech (2015) 782:567–93. doi:10.1017/jfm.2015.551 ｜ [🔗 DOI](https://doi.org/10.1017/jfm.2015.551) ^ref-26
- **[27]** Guseva K, Daitche A, Feudel U, Tél T. History effects in the sedimentation of light aerosols in turbulence: The case of marine snow. Phys Rev Fluids 1 (2016) 1:074203. doi:10.1103/physrevﬂuids.1.074203 ｜ [🔗 DOI](https://doi.org/10.1103/physrev%EF%AC%82uids.1.074203) ^ref-27
- **[28]** van Hinsberg MAT, Clercx HJH, Toschi F. Enhanced settling of nonheavy inertial particles in homogeneous isotropic turbulence: The role of the pressure gradient and the Basset history force. Phys Rev E 95 (2017) 95:023106. doi:10.1103/physreve.95.023106023106 ｜ [🔗 DOI](https://doi.org/10.1103/physreve.95.023106023106) ^ref-28
- **[29]** Haller G. Solving the inertial particle equation with memory. J Fluid Mech (2019) 874:1–4. doi:10.1017/jfm.2019.378 ｜ [🔗 DOI](https://doi.org/10.1017/jfm.2019.378) ^ref-29
- **[30]** Ling Y, Parmar M, Balachandar S. A scaling analysis of added-mass and history forces and their coupling in dispersed multiphase ﬂows. Int J Multiphase Flow (2013) 57: 102–14. doi:10.1016/j.ijmultiphaseﬂow.2013.07.005 ｜ [🔗 DOI](https://doi.org/10.1016/j.ijmultiphase%EF%AC%82ow.2013.07.005) ^ref-30
- **[31]** Li Z, Wei J, Bu S, Yu B. A frequency analysis method to estimate the relative importance of Basset force on small particles in turbulence. Int J Multiphase Flow (2021) 139:103640. doi:10.1016/j.ijmultiphaseﬂow.2021.103640 ｜ [🔗 DOI](https://doi.org/10.1016/j.ijmultiphase%EF%AC%82ow.2021.103640) ^ref-31
- **[32]** Mei R. Velocity ﬁdelity of ﬂow tracer particles. Exp Fluids (1996) 22:1–13. doi:10. 1007/bf01893300 ^ref-32
- **[33]** Michaelides EE. Review—the transient equation of motion for particles, bubbles, and droplets. ASME J Fluids Eng (1997) 119:233–47. doi:10.1115/1.2819127 ｜ [🔗 DOI](https://doi.org/10.1115/1.2819127) ^ref-33
- **[34]** Magnaudet J, Eames I. The motion of high-Reynolds-number bubbles in inhomogeneous ﬂows. Annu Rev Fluid Mech (2000) 32:659–708. doi:10.1146/ annurev.ﬂuid.32.1.659 ^ref-34
- **[35]** Boussinesq J. Sur la résistance qu’oppose un liquide indéﬁni au repos au mouvement varié d’une sphère solide. C R Acad Sci Paris (1885) 100:935–7. ^ref-35
- **[36]** Basset A. Treatise on hydrodynamics (deighton, bell and company) (1888). ^ref-36
- **[37]** Mei R, Adrian R. Flow past a sphere with an oscillation in the free-stream velocity and unsteady drag at ﬁnite Reynolds number. J Fluid Mech (1992) 237:323–41. doi:10. 1017/s0022112092003434 ^ref-37
- **[38]** Lovalenti PM, Brady JF. The force on a sphere in a uniform ﬂow with smallamplitude oscillations at ﬁnite Reynolds number. J Fluid Mech (1993) 256:607–14. doi:10.1017/s0022112093002897 ｜ [🔗 DOI](https://doi.org/10.1017/s0022112093002897) ^ref-38
- **[39]** Candelier F, Mehlig B, Magnaudet J. Time-dependent lift and drag on a rigid body in a viscous steady linear ﬂow. J Fluid Mech (2019) 864:554–95. doi:10.1017/jfm.2019.23 ｜ [🔗 DOI](https://doi.org/10.1017/jfm.2019.23) ^ref-39
- **[40]** Candelier F, Mehaddi R, Mehlig B, Magnaudet J. Second-order inertial forces and torques on a sphere in a viscous steady linear ﬂow. J Fluid Mech (2023) 954:A25. doi:10. 1017/jfm.2022.1015 ^ref-40
- **[41]** Gatignol R. On the history term of Boussinesq–Basset when the viscous ﬂuid slips on the particle. Comptes Rendus Mécanique (2007) 335:606–16. doi:10.1016/j.crme.2007.08.013 ｜ [🔗 DOI](https://doi.org/10.1016/j.crme.2007.08.013) ^ref-41
- **[42]** Premlata AR, Wei H-H Atypical non-Basset particle dynamics due to hydrodynamic slip. Phys Fluids 32 (2020) 32:097109. doi:10.1063/5.0021986 ｜ [🔗 DOI](https://doi.org/10.1063/5.0021986) ^ref-42
- **[43]** Yang S, Leal LG. A note on memory-integral contributions to the force on an accelerating spherical drop at low Reynolds number. Phys Fluids A (1991) 3:1822–4. doi:10. 1063/1.858202 ^ref-43
- **[44]** Galindo V, Gerbeth G. A note on the force on an accelerating spherical drop at low-Reynolds number. Phys Fluids A (1993) 5:3290–2. doi:10.1063/1.858686 ｜ [🔗 DOI](https://doi.org/10.1063/1.858686) ^ref-44
- **[45]** Abbad M, Souhar M. Experimental investigation on the history force acting on oscillating ﬂuid spheres at low Reynolds number. Phys Fluids (2004) 16:3808–17. doi:10.1063/1.1779051 ｜ [🔗 DOI](https://doi.org/10.1063/1.1779051) ^ref-45
- **[46]** Garbin V, Dollet B, Overvelde M, Cojoc D, Di Fabrizio E, van Wijngaarden L, et al. History force on coated microbubbles propelled by ultrasound. Phys Fluids 21 (2009) 21: 092003. doi:10.1063/1.3227903092003 ｜ [🔗 DOI](https://doi.org/10.1063/1.3227903092003) ^ref-46
- **[47]** Daitche A. Advection of inertial particles in the presence of the history force: Higher order numerical schemes. J Comput Phys (2013) 254:93–106. doi:10.1016/j.jcp.2013.07.024 ｜ [🔗 DOI](https://doi.org/10.1016/j.jcp.2013.07.024) ^ref-47
- **[48]** Moreno-Casas PA, Bombardelli FA. Computation of the Basset force: Recent advances and environmental ﬂow applications. Environ Fluid Mech (2016) 16:193–208. doi:10.1007/s10652-015-9424-1 ｜ [🔗 DOI](https://doi.org/10.1007/s10652-015-9424-1) ^ref-48
- **[49]** Garrappa R, Popolizio M. Generalized exponential time differencing methods for fractional order problems. Comput Math Appl (2011) 62:876–90. doi:10.1016/j.camwa.2011.04.054 ｜ [🔗 DOI](https://doi.org/10.1016/j.camwa.2011.04.054) ^ref-49
- **[50]** Garrappa R. Numerical solution of fractional differential equations: A survey and a software tutorial. Mathematics (2018) 6:16. doi:10.3390/math6020016 ｜ [🔗 DOI](https://doi.org/10.3390/math6020016) ^ref-50
- **[51]** Cox SM, Matthews PC. Exponential time differencing for stiff systems. J Comput Phys (2002) 176:430–55. doi:10.1006/jcph.2002.6995 ｜ [🔗 DOI](https://doi.org/10.1006/jcph.2002.6995) ^ref-51
- **[52]** Brush LM, Ho H-W, Yen B-C. Accelerated motion of a sphere in a viscous ﬂuid. J Hydraul Eng (1964) 90:149–60. doi:10.1061/jyceaj.0000973 ｜ [🔗 DOI](https://doi.org/10.1061/jyceaj.0000973) ^ref-52
- **[53]** van Hinsberg M, ten Thije Boonkkamp J, Clercx H. An efﬁcient, second order method for the approximation of the Basset history force. J Comput Phys (2011) 230: 1465–78. doi:10.1016/j.jcp.2010.11.014 ｜ [🔗 DOI](https://doi.org/10.1016/j.jcp.2010.11.014) ^ref-53
- **[54]** Bombardelli F, González A, Niño Y. Computation of the particle Basset force with a fractional-derivative approach. J Hydraul Eng (2008) 134:1513–20. doi:10.1061/(asce) 0733-9429(2008)134:10(1513) ^ref-54
- **[55]** Dorgan A, Loth E. Efﬁcient calculation of the history force at ﬁnite Reynolds numbers. Int J Multiphase Flow (2007) 33:833–48. doi:10.1016/j.ijmultiphaseﬂow.2007.02.005 ｜ [🔗 DOI](https://doi.org/10.1016/j.ijmultiphase%EF%AC%82ow.2007.02.005) ^ref-55
- **[56]** Parmar M, Annamalai S, Balachandar S, Prosperetti A. Differential formulation of the viscous history force on a particle for efﬁcient and accurate computation. J Fluid Mech (2018) 844:970–93. doi:10.1017/jfm.2018.217 ｜ [🔗 DOI](https://doi.org/10.1017/jfm.2018.217) ^ref-56
- **[57]** Beylkin G, Monzón L. On approximation of functions by exponential sums. Appl Comput Harmon Anal (2005) 19:17–48. doi:10.1016/j.acha.2005.01.003 ｜ [🔗 DOI](https://doi.org/10.1016/j.acha.2005.01.003) ^ref-57
- **[58]** Casas G, Ferrer A, Oñate E. Approximating the Basset force by optimizing the method of van Hinsberg et al. J Comput Phys (2018) 352:142–71. doi:10.1016/j.jcp.2017.09.060 ｜ [🔗 DOI](https://doi.org/10.1016/j.jcp.2017.09.060) ^ref-58
- **[59]** Sano T. Unsteady ﬂow past a sphere at low Reynolds number. J Fluid Mech (1981) 112:433–41. doi:10.1017/s0022112081000499 ｜ [🔗 DOI](https://doi.org/10.1017/s0022112081000499) ^ref-59
- **[60]** Bentwich M, Miloh T. The unsteady matched Stokes-Oseen solution for the ﬂow past a sphere. (1978) 88:17–32. s0022112078001962 ^ref-60
<!--/REFS_AUTO-->