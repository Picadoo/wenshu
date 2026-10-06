# 摘要、引言与方法的结构例子

需要具体范例时，仅查阅当前章节及适合研究的类型。本文件汇合原先分散的正文例子，目录名称用于定位，不依赖旧文件路径。模板、论文片段和变量占位只说明表达结构；不能抄作目标研究事实或照搬论文原句。

选择顺序：先确定问题、证据及章节职责，再选组织方式。方法论文、现象发现和综述不强制使用同一种叙述；例子来自特定领域，其性能指标、优势和创新性都须回到作者材料验证。

## 选择索引

- 摘要：challenge→contribution、challenge→insight→contribution、多项独立贡献；中心主张与决定性支持优先于套句数。
- 引言：任务先行、应用先行、一般到具体场景、挑战先行；已有任务的挑战链、传统思想支持的洞见、新任务分解；一种贡献多优势、两项贡献、原流程的新模块、观察驱动。
- 方法：模块三要素、forward process、overview、清晰度问题；依据已有方法写输入—步骤—输出，不制造 pipeline。

以下标题含原资料名称，查阅匹配小节即可。不是每次加载全部范例。

## abstract/template-a.md

## Abstract Template A Examples (Challenge -> Contribution)

Source scope: your original notes, "Version 1".

```latex
\section{Abstract}
% Task
% Technical challenge for previous methods (discuss around the technical challenge that we solved)
% Introduce the technical contribution for solving the challenge in one to two sentences (usually mention the technical term/name only, without describing every detailed step. The term should be easy to understand and should not create a jump in reading. This ability is very important for writing a good abstract.)
% Introduce the benefits of the technical contribution
% Experiment
```

### Reusable skeleton

1. `[Task sentence]`
2. `However, previous methods suffer from [technical challenge].`
3. `To solve this challenge, we propose [technical contribution name].`
4. `[One more contribution sentence if needed].`
5. `This contribution brings [technical benefit].`
6. `Experiments show [main result].`

## abstract/template-b.md

## Abstract Template B Examples (Challenge -> Insight -> Contribution)

```latex
\section{Abstract}
% Task
%% Example 1: In recent years, generative models have undergone significant advancement due to the success of diffusion models.
%% Example 2: This paper addresses the challenge of novel view synthesis for a human performer from a very sparse set of camera views.

% Technical challenge for previous methods (discuss around the technical challenge that we solved)
%% Example 1: The success of these models is often attributed to their use of guidance techniques, such as classifier and classifier-free methods, which provides effective mechanisms to tradeoff between fidelity and diversity. However, these methods are not capable of guiding a generated image to be aware of its geometric configuration, e.g., depth, which hinders the application of diffusion models to areas that require a certain level of depth awareness.
%% Example 2: Some recent works have shown that learning implicit neural representations of 3D scenes achieves remarkable view synthesis quality given dense input views. However, the representation learning will be ill-posed if the views are highly sparse.

% Introduce the insight for solving the challenge in one sentence
%% Example 1: To address this limitation, we propose a novel guidance approach for diffusion models that uses estimated depth information derived from the rich intermediate representations of diffusion models.
%% Example 2: To solve this ill-posed problem, our key idea is to integrate observations over video frames.

% Introduce the technical contribution that implements the insight in one to two sentences (usually mention the technical term/name only, without describing every detailed step. The term should be easy to understand and should not create a jump in reading. This ability is very important for writing a good abstract.)
%% Example 1: To do this, we first present a label-efficient depth estimation framework using the internal representations of diffusion models. At the sampling phase, we utilize two guidance techniques to self-condition the generated image using the estimated depth map, the first of which uses pseudo-labeling, and the subsequent one uses a depth-domain diffusion prior.
%% Example 2: To this end, we propose Neural Body, a new human body representation which assumes that the learned neural representations at different frames share the same set of latent codes anchored to a deformable mesh

% Introduce the benefits of technical novelty
%% Example 2: so that the observations across frames can be naturally integrated. The deformable mesh also provides geometric guidance for the network to learn 3D representations more efficiently.

% Experiment
```

### Given example pattern 2

1. `This paper addresses the challenge of novel view synthesis for a human performer from a very sparse set of camera views.`
2. `... representation learning will be ill-posed if the views are highly sparse.`
3. `To solve this ill-posed problem, our key idea is to integrate observations over video frames.`
4. `To this end, we propose Neural Body ...`
5. `... observations across frames can be naturally integrated ... provides geometric guidance ...`
6. `Experiments show [main result].`

## abstract/template-c.md

## Abstract Template C Examples (Multiple Contributions)

```latex
% Task
%% This paper introduces a novel contour-based approach named deep snake for real-time instance segmentation.

%% Unlike some recent methods that directly regress the coordinates of the object boundary points from an image

% Introduce technical contribution and technical advantage in one sentence (this ability is very important for writing a good abstract.)
%% deep snake uses a neural network to iteratively deform an initial contour to match the object boundary, which implements the classic idea of snake algorithms with a learning-based approach.

% Introduce technical contribution and technical advantage in one sentence
%% For structured feature learning on the contour, we propose to use circular convolution in deep snake, which better exploits the cycle-graph structure of a contour compared against generic graph convolution.

% Introduce technical contribution and technical advantage in one sentence
%% Based on deep snake, we develop a two-stage pipeline for instance segmentation: initial contour proposal and contour deformation, which can handle errors in object localization.

% Experiment
```

### Given example pattern (Deep Snake style from your text)

1. `This paper introduces a novel contour-based approach named deep snake for real-time instance segmentation.`
2. `Unlike some recent methods that directly regress the coordinates of the object boundary points from an image ...`
3. `deep snake uses a neural network to iteratively deform an initial contour ...`
4. `For structured feature learning on the contour, we propose circular convolution ...`
5. `Based on deep snake, we develop a two-stage pipeline ...`
6. `Experiments show [main result].`

## introduction/novel-task-challenge-decomposition.md

## Introduction Novel-Task Challenge Decomposition


`For novel tasks without direct methods, decompose the challenge into clear requirement/challenge points.`

```latex
% To achieve xx goal, several requirements must be satisfied (or several challenges must be handled).
%% Example: In this work, our goal is to build a model that captures such object intrinsics from a single image. This problem is challenging for three reasons.

% Describe point 1
%% Example: First, we only have a single image. This makes our work fundamentally different from existing works on 3D-aware image generation models [8, 9, 27, 28], which typically require a large dataset of thousands of instances for training. In comparison, the single image contains at most a few dozen instances, making the inference problem highly under-constrained.

% Describe point 2
%% Example: Second, these already limited instances may vary significantly in pixel values. This is because they have different poses and illumination conditions, but neither of these factors are annotated or known. We also cannot resort to existing tools for pose estimation based on structure from motion, such as COLMAP [35], because the appearance variations violate the assumptions of epipolar geometry.

% Describe point 3
%% Example: Finally, the object intrinsics we aim to infer are probabilistic, not deterministic: no two roses in the natural world are identical, and we want to capture a distribution of their geometry, texture, and material to exploit the underlying multi-view information.
```

## introduction/pipeline-not-recommended-abstract-only.md

## Not Recommended: Abstract-Only Method Description in Introduction


`Not recommended: If the method is simple, do not avoid concrete method details in Introduction and only discuss abstract insight to make it look novel.`

Expert note (faithful translation):

1. The craft of this writing template is how to make a simple pipeline look novel.
2. Note: this is not about making the insight look novel, but about making the pipeline steps look novel.
3. In most cases this is not recommended.
4. The better target is to clearly explain how the core contribution is implemented in Introduction.

```latex
% To tackle this problem, we propose a novel 3D GAN training method to generate photo-realistic images irrespective of the viewing angle.

% Introduce key idea
% Our key idea is as follows. To ease the challenging problem of learning photorealistic and multi-view consistent image synthesis, we cast the problem into two subproblems, each of which can be solved more easily.

% Explain why the key idea works, but without concretely discussing the full pipeline (or only discuss abstract benefit)
%% Example: Specifically, we formulate the problem as a combination of two simple discrimination problems, one of which learns to discriminate whether a synthesized image looks real or not, and the other learns to discriminate whether a synthesized image agrees with the camera pose. Unlike the formulations of the previous methods, which try to learn the real image distribution for each pose, or to learn pose estimation, our subproblems are much easier as each of them is analogous to a basic binary classification problem.

% Introduce pipeline modules with new terms but without clearly explaining the full pipeline (or skip concrete pipeline details)
%% Example: Based on this key idea, we propose a dual-branched discriminator, which has two branches for learning photorealism and pose consistency, respectively. As these branches are supervised explicitly for their respective purposes, high-quality images with pose consistency can be produced at each viewing angle, and consequently, the generator creates high-quality images and shapes. (This paragraph does not clearly explain how the pipeline works.)

% Introduce another contribution
%% Example: In addition, we propose a pose-matching loss to give supervision to the discriminator for the pose consistency, by considering a positive pose (i.e., rendering pose or ground truth pose) and a negative pose (i.e., irrelevant pose) for a given image. (This paragraph does not clearly explain how the pipeline works.)

% Explain expected benefit over prior methods
%% Example: For example, the frontal viewpoint is one of the irrelevant poses for a side-view image. As reported in the experiments, this loss helps improve image and shape quality. This can be interpreted as a simplification of a classification problem from a large number of classes into binary, which is composed of positive and negative pairs.
```

## introduction/pipeline-version-1-one-contribution-multi-advantages.md

## Pipeline Version 1 (One Contribution, Multiple Advantages)


`Version 1: One contribution with multiple advantages, and one teaser figure to present the basic idea.`

```latex
% In this paper, we propose a novel framework …
%% Example: In this paper, we introduce a novel implicit neural representation for dynamic humans, named Neural Body, to solve the challenge of novel view synthesis from sparse views.
In this paper, we propose a novel framework/representation, named [method name] for [xxx task].

% Teaser for basic idea
%% Example: The basic idea is illustrated in Figure 2.
The basic idea is illustrated in [xxx Figure].

% One-sentence key novelty/contribution (very important ability)
%% Example: For the implicit fields at different frames, instead of learning them separately, Neural Body generates them from the same set of latent codes.
Our innovation is in [one sentence for key novelty].

% Method details
%% Example: Specifically, we anchor a set of latent codes to the vertices of a deformable human model (SMPL in this work), namely that their spatial locations vary with the human pose. To obtain the 3D representation at a frame, we first transform the code locations based on the human pose, which can be reliably estimated from sparse camera views. Then, a network is designed to regress the density and color for any 3D point based on these latent codes. Both the latent codes and the network are jointly learned from images of all video frames during the reconstruction.
Specifically, [how it works in detail].

% Advantage 1
%% Example: This model is inspired by the latent variable model in statistics, which enables us to effectively integrate observations at different frames.
In contrast to previous methods, [our advantage].

% Advantage 2
%% Example: Another advantage of the proposed method is that the deformable model provides a geometric prior (rough surface location) to enable more efficient learning of implicit fields.
Another advantage of the proposed method is that [another advantage].
```

## introduction/pipeline-version-2-two-contributions.md

## Pipeline Version 2 (Two Contributions)


`Version 2: Two contributions, and one teaser figure to present the basic idea.`

```latex
% In this paper, we propose a novel framework …
%% Example: In this paper, we introduce a novel implicit neural representation for dynamic humans, named Neural Body, to solve the challenge of novel view synthesis from sparse views.
In this paper, we propose a novel framework/representation, named [method name] for [xxx task].

% One-sentence key novelty
%% Example: To that end, we propose techniques to represent a given subject with rare token identifiers and fine-tune a pre-trained, diffusion-based text-to-image framework that operates in two steps; generating a low-resolution image from text and subsequently applying super-resolution (SR) diffusion models.
Our innovation is in [one sentence for key novelty].

% Teaser
%% Example: The basic idea is illustrated in Figure 2.
The basic idea is illustrated in [xxx Figure].

% Contribution 1 details
%% Example: We first fine-tune the low-resolution text-to-image model with the input images and text prompts containing a unique identifier followed by the class name of the subject (e.g., “A [V] dog”).
Specifically, [how contribution 1 works].

% Advantage of contribution 1
%% Example: This model is inspired by the latent variable model in statistics, which enables us to effectively integrate observations at different frames.
In contrast to previous methods, [advantage of contribution 1].

% Challenge motivating contribution 2
%% Example: In order to prevent overfitting and language drift [35, 40] that cause the model to associate the class name (e.g., “dog”) with the specific instance
However, [another technical challenge].

% Contribution 2 details
%% Example: we propose an autogenous, class-specific prior preservation loss, which leverages the semantic prior on the class that is embedded in the model, and encourages it to generate diverse instances of the same class as our subject.
Specifically, [how contribution 2 works].
```

## introduction/pipeline-version-3-new-module-on-existing-pipeline.md

## Pipeline Version 3 (New Module on Existing Pipeline)


`Version 3: Build on a prior pipeline and introduce one new module, with a teaser figure for the basic idea.`

```latex
% In this paper, we propose a learning-based snake algorithm, named deep snake, for real-time instance segmentation.

% Inspired by previous methods [21, 25], deep snake takes an initial contour as input and deforms it by regressing vertex-wise offsets.

% Our innovation is introducing the circular convolution for efficient feature learning on a contour, as illustrated in Figure 1.

% We observe that the contour is a cycle graph that consists of a sequence of vertices connected in a closed cycle. Since every vertex has the same degree equal to two, we can apply the standard 1D convolution on the vertex features.

% Considering that the contour is periodic, deep snake introduces the circular convolution, which indicates that an aperiodic function (1D kernel) is convolved in the standard way with a periodic function (features defined on the contour).

% The kernel of circular convolution encodes not only the feature of each vertex but also the relationship among neighboring vertices. In contrast, the generic GCN performs pooling to aggregate information from neighboring vertices. The kernel function in our circular convolution amounts to a learnable aggregation function, which is more expressive and results in better performance than using a generic GCN, as demonstrated by our experimental results in Section 5.2.
```

## introduction/pipeline-version-4-observation-driven.md

## Pipeline Version 4 (Observation-Driven Contribution)


`Version 4: Contribution comes from one important observation. Introduce key innovation first, then intuitive observation as motivation, then method details, then benefits.`

```latex
% In this paper, we propose a learning-based snake algorithm, named deep snake, for real-time instance segmentation.

% Our innovation is introducing the circular convolution for efficient feature learning on a contour, as illustrated in Figure 1.

% We observe that the contour is a cycle graph that consists of a sequence of vertices connected in a closed cycle. Since every vertex has the same degree equal to two, we can apply the standard 1D convolution on the vertex features.

% Considering that the contour is periodic, deep snake introduces the circular convolution, which indicates that an aperiodic function (1D kernel) is convolved in the standard way with a periodic function (features defined on the contour).

% The kernel of circular convolution encodes not only the feature of each vertex but also the relationship among neighboring vertices. In contrast, the generic GCN performs pooling to aggregate information from neighboring vertices. The kernel function in our circular convolution amounts to a learnable aggregation function, which is more expressive and results in better performance than using a generic GCN, as demonstrated by our experimental results in Section 5.2.
```

## introduction/technical-challenge-version-1-existing-task.md

## Technical Challenge Version 1 (Existing Task, Existing Methods)


`Version 1: For existing tasks with existing methods, discuss the challenge chain from traditional methods to recent methods and finally to the challenge we solve.`

```latex
% Discuss general technical challenges of this task (to lead into recent methods)
%% Example 1: This problem is quite challenging from many perspectives, including object detection under severe occlusions, variations in lighting and appearance, and cluttered background objects.
%% Example 2: This problem is particularly challenging due to the inherent ambiguity on acquiring human geometry, materials and motions from images.
This problem is particularly challenging due to several factors, including [xxx reason], [xxx reason], and [xxx reason].

% Briefly introduce one class of traditional methods, then discuss their technical challenge
%% Example: Traditional methods have shown that pose estimation can be achieved by establishing the correspondences between an object image and the object model.
To overcome these challenges, traditional methods [how they work], [what they achieve].

%% Example: They rely on hand-crafted features, which are not robust to image variations and background clutters.
However, they [technical challenge they face].

% Briefly introduce one class of recent methods 1 (optional), then discuss their challenge
%% Example: Deep learning based methods train end-to-end neural networks that take an image as input and output its corresponding pose.
Recently, [xxx methods] [how they work], [what they achieve].

%% Example: However, generalization remains as an issue, as it is unclear that such end-to-end methods learn sufficient feature representations for pose estimation.
However, they [limitation], because [xxx technical reason].

% Briefly introduce one class of recent methods 2, then discuss their challenge (must lead to our solved challenge)
%% Example: Some recent methods use CNNs to first regress 2D keypoints and then compute 6D pose parameters using the Perspective-n-Point (PnP) algorithm. In other words, the detected keypoints serve as an intermediate representation for pose estimation. Such two-stage approaches achieve state-of-the-art performance, thanks to robust detection of keypoints.
To overcome this challenge, [xxx methods] [how they work], [what they achieve].

%% Example: However, these methods have difficulty in tackling occluded and truncated objects, since part of their keypoints are invisible. Although CNNs may predict these unseen keypoints by memorizing similar patterns, generalization remains difficult.
However, they [limitation], because [xxx technical reason].
```

## introduction/technical-challenge-version-2-existing-task-insight-backed-by-traditional.md

## Technical Challenge Version 2 (Existing Task, Insight Backed by Traditional Methods)


`Version 2: For existing tasks, if our technical insight was used in traditional methods, discuss that line to provide conceptual backing.`

```latex
% Introduce one class of traditional/recent methods and discuss their technical challenge (to lead to our insight)
%% Example (Deep Snake): Most of the state-of-the-art instance segmentation methods perform pixel-wise segmentation within a bounding box given by an object detector.
%% Example (ManhattanSDF): Given input images, traditional methods generally estimate the depth map for each image based on the multi-view stereo (MVS) algorithms and then fuse estimated depth maps into 3D models.
Traditional/recent methods [how they work], [what they achieve].

%% Example (Deep Snake): They may be sensitive to the inaccurate bounding box. Moreover, representing an object shape as dense binary pixels generally results in costly post-processing.
%% Example (ManhattanSDF): Although these methods achieve successful reconstruction in most cases, they have difficulty in handling low-textured regions, e.g., floors and walls of indoor scenes, due to the unreliable stereo matching in these regions.
However, they [limitation], because [xxx technical reason].

% Discuss traditional methods that used an insight similar to ours (implicitly backing our idea)
%% Example (Deep Snake): An alternative shape representation is the object contour, which is a set of vertices along the object silhouette. In contrast to pixel-based representation, a contour is not limited within a bounding box and has fewer parameters. Such a contour-based representation has long been used in image segmentation since the seminal work by Kass et al., which is well known as snakes or active contours.
%% Example (ManhattanSDF): To improve the reconstruction of low-textured regions, a typical approach is leveraging the planar prior of manmade scenes, which has long been explored in literature. A renowned example is the Manhattanworld assumption, i.e., the surfaces of man-made scenes should be aligned with three dominant directions.
To overcome this problem, a typical approach is [xxx insight], which has long been explored in literature.

These methods [how they work].

%% Example (Deep Snake): While many variants have been developed in literature, these methods are prone to local optima as the objective functions are handcrafted and typically nonconvex.
%% Example (ManhattanSDF): However, all of them focus on optimizing per-view depth maps instead of the full scene models in 3D space. As a result, depth estimation and plane segmentation could still be inconsistent among views, yielding suboptimal reconstruction quality as demonstrated by our experimental results in Section 5.3.
However, they [limitation], because [xxx technical reason].

% Then discuss newer methods and their remaining challenge (must lead to our solved challenge)
%% Example: There is a recent trend to represent 3D scenes as implicit neural representations and learn the representations from images with differentiable renderers. In particular, [49, 54, 55] use a signed distance field (SDF) to represent the scene and render it into images based on the sphere tracing or volume rendering. Thanks to the well-defined surfaces of SDFs, they recover high-quality 3D geometries from images.
To overcome this challenge, [xxx methods] [how they work], [what they achieve].

%% Example: However, these methods essentially rely on the multi-view photometric consistency to learn the SDFs. So they still suffer from poor performance in low-textured planar regions, as shown in Figure 1, as many plausible solutions may satisfy the photometric constraint in low-textured planar regions.
However, they [limitation], because [xxx technical reason].
```

## introduction/technical-challenge-version-3-novel-task.md

## Technical Challenge Version 3 (Novel Task)


`Version 3: For novel tasks without direct methods, define the challenge directly and decompose it by requirement/challenge points.`

```latex
% To achieve xx goal, several requirements/challenges must be satisfied.
%% Example: In this work, our goal is to build a model that captures such object intrinsics from a single image. This problem is challenging for three reasons.

% Describe point 1
%% Example: First, we only have a single image. This makes our work fundamentally different from existing works on 3D-aware image generation models [8, 9, 27, 28], which typically require a large dataset of thousands of instances for training. In comparison, the single image contains at most a few dozen instances, making the inference problem highly under-constrained.

% Describe point 2
%% Example: Second, these already limited instances may vary significantly in pixel values. This is because they have different poses and illumination conditions, but neither of these factors are annotated or known. We also cannot resort to existing tools for pose estimation based on structure from motion, such as COLMAP [35], because the appearance variations violate the assumptions of epipolar geometry.

% Describe point 3
%% Example: Finally, the object intrinsics we aim to infer are probabilistic, not deterministic: no two roses in the natural world are identical, and we want to capture a distribution of their geometry, texture, and material to exploit the underlying multi-view information.
```

See also:
1. `references/examples/introduction/novel-task-challenge-decomposition.md`

## introduction/version-1-task-then-application.md

## Introduction Version 1: Task First, Then Application


`Version 1: If the task is relatively niche, introduce the task first, then introduce applications.`

```latex
% Introduce Task (if the task is very familiar, this part can be skipped)
%% Example: Object pose estimation aims to estimate object's orientation and translation relative to a canonical frame from a single image.
[xxx task] targets at recovering/reconstructing/estimating [xxx output] from [xxx input].

% Introduce Application
%% Example: Accurate pose estimation is essential for a variety of applications such as augmented reality, autonomous driving and robotic manipulation.
[xxx task] has a variety of applications such as [xxx], [xxx], and [xxx].
```

## introduction/version-2-application-first.md

## Introduction Version 2: Application First


`Version 2: If the task is already familiar to most readers, introduce applications directly.`

```latex
% Introduce Application
%% Example: Accurate pose estimation is essential for a variety of applications such as augmented reality, autonomous driving and robotic manipulation.
[xxx task] has a variety of applications such as [xxx], [xxx], and [xxx].
```

## introduction/version-3-general-to-specific-setting.md

## Introduction Version 3: General Application -> Specific Setting


`Version 3: Introduce applications of the general task first, then introduce the specific task setting. (Personally recommended when the setting is relatively new.)`

```latex
% Introduce applications of the general task
%% Example: Accurate pose estimation is essential for a variety of applications such as augmented reality, autonomous driving and robotic manipulation.
[xxx task] has a variety of applications such as [xxx], [xxx], and [xxx].

% Introduce the specific task setting
%% Example: This paper focuses on the specific setting of recovering the 6DoF pose of an object, i.e., rotation and translation in 3D, from a single RGB image of that object.
This paper focuses on the specific setting of recovering/reconstructing/estimating [xxx output] from [xxx input].
```

## introduction/version-4-open-with-challenge.md

## Introduction Version 4: Open with Application and Challenge


`Version 4: If the task is familiar, introduce applications directly and expose the target technical challenge in the opening paragraph via previous methods.`

Expert notes (faithful translation):

1. It is often good if the opening paragraph already states what we want to solve.
2. But this style requires suitable conditions and is less common.
3. Usually, several prior-method paragraphs are still needed before the target challenge becomes clear.

```latex
% Introduce Application
%% Example 1: Reconstructing 3D scenes from multi-view images is a cornerstone of many applications such as augmented reality, robotics, and autonomous driving.
%% Example 2: Instance segmentation is the cornerstone of many computer vision tasks, such as video analysis, autonomous driving, and robotic grasping, which require both accuracy and efficiency.

% Use previous methods to expose the target technical challenge
%% Example 1: Given input images, traditional methods [43, 44, 59] generally estimate the depth map for each image based on the multi-view stereo (MVS) algorithms and then fuse estimated depth maps into 3D models. Although these methods achieve successful reconstruction in most cases, they have difficulty in handling low-textured regions, e.g., floors and walls of indoor scenes, due to the unreliable stereo matching in these regions.
%% Example 2: Most of the state-of-the-art instance segmentation methods [18, 27, 5, 19] perform pixel-wise segmentation within a bounding box given by an object detector [36], which may be sensitive to the inaccurate bounding box. Moreover, representing an object shape as dense binary pixels generally results in costly post-processing.
```

## method/example-of-the-three-elements.md

## Example of the Three Elements

This example uses `%` comments as annotations.
Each `% ...` annotation explains the paragraph(s) immediately below it.

```latex
\begin{quote}
\textbf{Annotation rule.} In this example, each line starting with \% labels the role of the paragraph(s) directly below it.
\end{quote}

\begin{itemize}
\item Module design (data structure)
\item Motivation of this module
\item Technical advantages of this module
\item Module design (forward process)
\end{itemize}

\subsection{3.1. Structured latent codes}

% Module design: introduce the module's data structure
To control the spatial locations of latent codes with the human pose, we anchor these latent codes to a deformable human body model (SMPL) [38]. SMPL is a skinned vertex-based model, which is defined as a function of shape parameters, pose parameters, and a rigid transformation relative to the SMPL coordinate system. The function outputs a posed 3D mesh with 6890 vertices. Specifically, we define a set of latent codes \( Z = \{z_1, z_2, ..., z_{6890}\} \) on vertices of the SMPL model. For the frame \( t \), SMPL parameters \( S_t \) are estimated from the multi-view images \( \{I_t^c \mid c = 1, ..., N_c\} \) using [26]. The spatial locations of the latent codes are then transformed based on the human pose \( S_t \) for the density and color regression. Figure 3 shows an example. The dimension of latent code \( z \) is set to 16 in our experiments.

% Technical advantages of this module
Similar to the local implicit representations [25, 5, 18], the latent codes are used with a neural network to represent the local geometry and appearance of a human. Anchoring these codes to a deformable model enables us to represent a dynamic human. With the dynamic human representation, we establish a latent variable model that maps the same set of latent codes to the implicit fields of density and color at different frames, which naturally integrates observations at different frames.

\subsection{3.2. Code diffusion}

% Motivation of this module
Figure 3(a) shows the process of code diffusion. The implicit fields assign the density and color to each point in the 3D space, which requires us to query the latent codes at continuous 3D locations. This can be achieved with the trilinear interpolation. However, since the structured latent codes are relatively sparse in the 3D space, directly interpolating the latent codes leads to zero vectors at most 3D points. To solve this problem, we diffuse the latent codes defined on the surface to nearby 3D space.

% Module design: introduce module design by describing the module forward process
Inspired by [65, 56, 49], we choose the SparseConvNet [21] to efficiently process the structured latent codes, whose architecture is described in Table 1. Specifically, based on the SMPL parameters, we compute the 3D bounding box of the human and divide the box into small voxels with voxel size of \( 5mm \times 5mm \times 5mm \). The latent code of a non-empty voxel is the mean of latent codes of SMPL vertices inside this voxel. SparseConvNet utilizes 3D sparse convolutions to process the input volume and output latent code volumes with \( 2\times, 4\times, 8\times, 16\times \) downsampled sizes. With the convolution and downsampling, the input codes are diffused to nearby space. Following [56], for any point in 3D space, we interpolate the latent codes from multi-scale code volumes of network layers 5, 9, 13, 17, and concatenate them into the final latent code. Since the code diffusion should not be affected by the human position and orientation in the world coordinate system, we transform the code locations to the SMPL coordinate system.

For any point \( \mathbf{x} \) in 3D space, we query its latent code from the latent code volume. Specifically, the point \( \mathbf{x} \) is first transformed to the SMPL coordinate system, which aligns the point and the latent code volume in 3D space. Then, the latent code is computed using the trilinear interpolation. For the SMPL parameters \( S_t \), we denote the latent code at point \( \mathbf{x} \) as \( \psi(\mathbf{x}, Z, S_t) \). The code vector is passed into MLP networks to predict the density and color for point \( \mathbf{x} \).

\subsection{3.3. Density and color regression}

Figure 3(b) overviews the regression of density and color for any point in 3D space. The density and color fields are represented by MLP networks. Details of network architectures are described in the supplementary material.

% Module design: introduce module design by describing the module forward process
\textbf{Density model.} For the frame \( t \), the volume density at point \( \mathbf{x} \) is predicted as a function of only the latent code \( \psi(\mathbf{x}, Z, S_t) \), which is defined as:

\[
\sigma_t(\mathbf{x}) = M_{\sigma}(\psi(\mathbf{x}, Z, S_t)),
\tag{1}
\]

where \( M_{\sigma} \) represents an MLP network with four layers.

% Module design: introduce the module's data structure
\textbf{Color model.} Similar to [37, 44], we take both the latent code \( \psi(\mathbf{x}, Z, S_t) \) and the viewing direction \( \mathbf{d} \) as input for the color regression. To model the location-dependent incident light, the color model also takes the spatial location \( \mathbf{x} \) as input. We observe that temporally-varying factors affect the human appearance, such as secondary lighting and self-shadowing. Inspired by the auto-decoder [48], we assign a latent embedding \( \ell_t \) for each video frame \( t \) to encode the temporally-varying factors.

% Module design: introduce module design by describing the module forward process
Specifically, for the frame \( t \), the color at \( \mathbf{x} \) is predicted as a function of the latent code \( \psi(\mathbf{x}, Z, S_t) \), the viewing direction \( \mathbf{d} \), the spatial location \( \mathbf{x} \), and the latent embedding \( \ell_t \). Following [51, 44], we apply the positional encoding to both the viewing direction \( \mathbf{d} \) and the spatial location \( \mathbf{x} \), which enables better learning of high frequency functions. The color model at frame \( t \) is defined as:

\[
c_t(\mathbf{x}) = M_c(\psi(\mathbf{x}, Z, S_t), \gamma_d(\mathbf{d}), \gamma_x(\mathbf{x}), \ell_t),
\tag{2}
\]

where \( M_c \) represents an MLP network with two layers, and \( \gamma_d \) and \( \gamma_x \) are positional encoding functions for viewing direction and spatial location, respectively. We set the dimension of \( \ell_t \) to 128 in experiments.

\subsection{3.4. Volume rendering}

% Module design: introduce module design by describing the module forward process
Given a viewpoint, we utilize the classical volume rendering techniques to render the Neural Body into a 2D image. The pixel colors are estimated via the volume rendering integral equation [27] that accumulates volume densities and colors along the corresponding camera ray. In practice, the integral is approximated using numerical quadrature [41, 44]. Given a pixel, we first compute its camera ray \( \mathbf{r} \) using the camera parameters and sample \( N_k \) points \( \{\mathbf{x}_k\}_{k=1}^{N_k} \) along camera ray \( \mathbf{r} \) between near and far bounds. The scene bounds are estimated based on the SMPL model. Then, Neural Body predicts volume densities and colors at these points. For the video frame \( t \), the rendered color \( \hat{C}_t(\mathbf{r}) \) ...
```

## method/method-writing-common-issues-note.md

## Method Writing Common Issues (Reference Note)

Original source mentioned in your notes:

1. `Method writing common issues (PDF in your source notes)`

Usage recommendation:

1. Use this reference as a troubleshooting checklist after drafting Method.
2. Prioritize unclear motivation, broken flow, missing implementation details, and inconsistent terms.

## method/module-design-instant-ngp.md

## Module Design Example

This example uses `%` comments as annotations.
Each `% ...` annotation explains the paragraph(s) immediately below it.

```latex
\begin{quote}
\textbf{Annotation rule.} In this example, each line starting with \% labels the role of the paragraph(s) directly below it.
\end{quote}

\begin{itemize}
\item Motivation of this module
\item Module design (data structure)
\item Module design (forward process)
\end{itemize}

\section{3 \quad MULTIRESOLUTION HASH ENCODING}

% Motivation of this module
Given a fully connected neural network \(m(y;\Phi)\), we are interested in an encoding of its inputs \(y=\operatorname{enc}(x;\theta)\) that improves the approximation quality and training speed across a wide range of applications without incurring a notable performance overhead.

% Module design: introduce the module's data structure
Our neural network not only has trainable weight parameters \(\Phi\), but also trainable encoding parameters \(\theta\). These are arranged into \(L\) levels, each containing up to \(T\) feature vectors with dimensionality \(F\). Typical values for these hyperparameters are shown in Table 1. Figure 3 illustrates the steps performed in our multiresolution hash encoding. Each level (two of which are shown as red and blue in the figure) is independent and conceptually stores feature vectors at the vertices of a grid, the resolution of which is chosen to be a geometric progression between the coarsest and finest resolutions \([N_{\min},N_{\max}]\):

\[
N_l := \left\lfloor N_{\min}\cdot b^l \right\rfloor, \tag{2}
\]

\[
b := \exp\!\left(\frac{\ln N_{\max}-\ln N_{\min}}{L-1}\right). \tag{3}
\]

\(N_{\max}\) is chosen to match the finest detail in the training data. Due to the large number of levels \(L\), the growth factor is usually small. Our use cases have \(b\in[1.26,2]\).

% Module design: introduce module design by describing the module forward process
Consider a single level \(l\). The input coordinate \(x\in\mathbb{R}^d\) is scaled by that level's grid resolution before rounding down and up:
\[
\lfloor x_l \rfloor := \lfloor x\cdot N_l \rfloor,\quad
\lceil x_l \rceil := \lceil x\cdot N_l \rceil.
\]

\(\lfloor x_l \rfloor\) and \(\lceil x_l \rceil\) span a voxel with \(2^d\) integer vertices in \(\mathbb{Z}^d\). We map each corner to an entry in the level's respective feature vector array, which has fixed size of at most \(T\). For coarser levels where a dense grid requires fewer than \(T\) parameters, i.e. \((N_l+1)^d \le T\), this mapping is 1:1. At finer levels, we use a hash function \(h:\mathbb{Z}^d\rightarrow\mathbb{Z}_T\) to index into the array, effectively treating it as a hash table, although there is no explicit collision handling. We rely instead on the gradient-based optimization to store appropriate sparse detail in the array, and the subsequent neural network \(m(y;\Phi)\) for collision resolution. The number of trainable encoding parameters \(\theta\) is therefore \(O(T)\) and bounded by \(T\cdot L\cdot F\), which in our case is always \(T\cdot16\cdot2\) (Table 1).

We use a spatial hash function [Teschner et al. 2003] of the form
\[
h(x)=\left(\bigoplus_{i=1}^{d} x_i\pi_i\right)\bmod T, \tag{4}
\]
where \(\oplus\) denotes the bit-wise XOR operation and \(\pi_i\) are unique, large prime numbers. Effectively, this formula XORs the results of a per-dimension linear congruential (pseudo-random) permutation [Lehmer 1951], \emph{decorrelating} the effect of the dimensions on the hashed value. Notably, to achieve (pseudo-)independence, only \(d-1\) of the \(d\) dimensions must be permuted, so we choose \(\pi_1:=1\) for better cache coherence, \(\pi_2=2{,}654{,}435{,}761\), and \(\pi_3=805{,}459{,}861\).

Lastly, the feature vectors at each corner are \(d\)-linearly interpolated according to the relative position of \(x\) within its hypercube, i.e. the interpolation weight is \(w_l := x_l-\lfloor x_l \rfloor\).

Recall that this process takes place independently for each of the \(L\) levels. The interpolated feature vectors of each level, as well as auxiliary inputs \(\xi\in\mathbb{R}^E\) (such as the encoded view direction and textures in neural radiance caching), are concatenated to produce \(y\in\mathbb{R}^{LF+E}\), which is the encoded input \(\operatorname{enc}(x;\theta)\) to the MLP \(m(y;\Phi)\).

\textbf{Performance vs. quality.} Choosing the hash table size \(T\) provides a trade-off between performance, memory and quality. Higher values of \(T\) result in higher quality and lower performance. The memory ...
```

## method/module-motivation-patterns.md

## Module Motivation Writing Patterns


`Module motivation is usually problem-driven: because a problem exists, we design xx to solve it.`

Typical opening sentences:

1. `A remaining problem/challenge is ...`
2. `However, we ...`
3. `Previous methods have difficulty in ...`

Usage note:

1. State the specific failure before introducing the module.
2. Keep motivation independent from implementation details.

## method/module-triad-neural-body.md

## Module Triad Example (Neural Body)

`Use Neural Body to understand the three elements of a module: design, motivation, and technical advantages.`

Local source references:

1. Annotated figure showing motivation/design/advantages split.
3. Text-converted annotation notes: `references/examples/method/neural-body-annotated-figure-text.md`

Triad mapping template:

1. Module design: what representation/network is built and how forward process runs.
2. Motivation: what unresolved challenge requires this module.
3. Technical advantages: why this module performs better than alternatives.

Direct usage:

1. Read `neural-body-annotated-figure-text.md` to map each paragraph to one triad element.
2. Rebuild your own Method subsection with the same triad order.

## method/neural-body-annotated-figure-text.md

## Neural Body Annotated Figure (Text Conversion)

This file converts the annotated Neural Body figure into reusable writing notes.

### Purpose

Use this mapping to understand how one Method section can explicitly separate:

1. Module motivation
2. Module design (data structure)
3. Module design (forward process)
4. Technical advantages

### Block-by-Block Mapping

#### Section 3.1: Structured Latent Codes

1. **Module design (data structure)**
- The paragraph defines structured latent codes anchored to the deformable human model (SMPL).
- It explains what is constructed (latent codes + their anchor positions + frame-dependent transformation by pose).

2. **Technical advantages**
- The paragraph explains why this design works better: dynamic-human representation and cross-frame integration of observations.
- It highlights why anchoring codes to deformable geometry is beneficial.

#### Section 3.2: Code Diffusion

1. **Motivation of this module**
- The paragraph states the remaining problem: direct interpolation of sparse structured codes leads to near-zero vectors at many 3D points.
- This motivates diffusion from surface codes to nearby 3D space.

2. **Module design (forward process)**
- The paragraph explains the execution pipeline: build sparse latent volumes, run sparse convolutions, interpolate latent codes at query points, and feed codes to prediction networks.
- This is a canonical input -> steps -> output module description.

#### Section 3.3: Density and Color Regression

1. **Module design (forward process) for density model**
- The density paragraph defines how density is regressed from latent code and frame condition.

2. **Module design (data structure) for color model**
- The color paragraph introduces required inputs/embeddings (latent code, view direction, spatial location, temporal embedding).

3. **Module design (forward process) for color model**
- The next paragraph describes how those inputs are encoded and passed into the color MLP for final color prediction.

#### Section 3.4: Volume Rendering

1. **Module design (forward process)**
- The paragraph describes ray sampling and volume integration to render image outputs from predicted density/color fields.

### Reusable Writing Pattern from This Figure

For each module subsection, follow this order:

1. `Motivation`: state unresolved challenge and technical reason.
2. `Design-1`: define structure/representation/network.
3. `Design-2`: describe forward process in execution order.
4. `Advantage`: explain why this module improves over alternatives.

### Suggested Paragraph Starters

1. Motivation: `A remaining challenge is ...`
2. Data structure design: `We represent ... with ...`
3. Forward process: `Given [input], we first ... then ... finally ...`
4. Technical advantage: `Compared with previous methods, this design ... because ...`

## method/overview-template.md

## Method Overview Template


`Overview usually includes setting, core contribution, optional figure pointer, and subsection map.`

```latex
% Overview
% One or two sentences for setting
%% Example 1: Given a sparse multi-view video of a performer, our task is to generate a free-viewpoint video of the performer.
%% Example 2: Given an image, the task of pose estimation is to detect objects and estimate their orientations and translations in the 3D space.

% One or two sentences for core contribution
%% Example 1: We build upon prior work for static scenes [46], to which we add the notion of time, and estimate 3D motion by explicitly modeling forward and backward scene flow as dense 3D vector fields.
%% Example 2: Inspired by [21, 25], we perform object segmentation by deforming an initial contour to match object boundary.
%% Example 3: Inspired by recent methods [29, 30, 36], we estimate the object pose using a two-stage pipeline: we first detect 2D object keypoints using CNNs and then compute 6D pose parameters using the PnP algorithm. Our innovation is in a new representation for 2D object keypoints as well as a modified PnP algorithm for pose estimation.

% If pipeline/framework is novel, point to figure
%% Example: The overview of the proposed model is illustrated in Figure 3.

% Explain what Section 3.1 covers
%% Example 1: Neural Body starts from a set of structured latent codes attached to the surface of a deformable human model (Section 3.1).
%% Example 2: In this section, we first describe how to model 3D scenes with MLP maps (Section 3.1).

% Explain what Section 3.2 covers
%% Example 1: The latent code at any location around the surface can be obtained with a code diffusion process (Section 3.2) and then decoded to density and color values by neural networks (Section 3.3).
%% Example 2: Then, Section 3.2 discusses how to represent volumetric videos with dynamic MLP maps.

% Explain what Section 3.3 covers
%% Example 3: Finally, we introduce some strategies to speed up the rendering process (Section 3.3).
```

## method/pre-writing-questions.md

## Method Pre-Writing Questions


`Before writing Method, answer: (1) what modules exist, and (2) for each module, what is its workflow, why is it needed, and why does it work.`

```text
Questions:
(1) What modules are in the method?
(2) For each module, answer three questions:
    - What is this module's workflow?
    - Why do we need this module?
    - Why does this module work?
```

Recommended action:

1. Organize answers in a mind map or table before writing paragraphs.
