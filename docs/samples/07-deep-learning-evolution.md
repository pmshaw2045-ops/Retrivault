# 深度学习模型架构演进

从 2012 年 AlexNet 到 2026 年的多模态大模型，深度学习架构经历了多次重大变革。

## 卷积神经网络（CNN）

CNN 的核心是卷积操作，通过局部感受野和权值共享大幅减少参数量。

### 经典架构

- **AlexNet（2012）**：5 层卷积 + 3 层全连接，ReLU 激活函数，首次在 ImageNet 上超越传统方法。
- **VGGNet（2014）**：统一使用 3×3 小卷积核，堆叠 16-19 层，证明深度比宽度更重要。
- **ResNet（2015）**：引入残差连接（Skip Connection），解决了深层网络退化问题，首次突破 100 层。
- **EfficientNet（2019）**：使用神经架构搜索（NAS）同时优化深度、宽度和分辨率。

```python
# 残差块示例
class ResidualBlock:
    def __init__(self, in_channels, out_channels):
        self.conv1 = Conv2d(in_channels, out_channels, 3)
        self.bn1 = BatchNorm(out_channels)
        self.conv2 = Conv2d(out_channels, out_channels, 3)
        self.bn2 = BatchNorm(out_channels)
        # 维度不匹配时使用 1×1 卷积投影
        self.shortcut = Conv2d(in_channels, out_channels, 1) if in_channels != out_channels else identity

    def forward(self, x):
        residual = self.shortcut(x)
        out = self.bn1(self.conv1(x)).relu()
        out = self.bn2(self.conv2(out))
        return (out + residual).relu()
```

## 循环神经网络（RNN）与 Transformer

RNN 按时间步处理序列，但存在长程依赖问题。

### LSTM 与 GRU

LSTM 通过输入门、遗忘门、输出门控制信息流动，有效缓解梯度消失。GRU 是 LSTM 的简化版本，合并了输入门和遗忘门。

### Transformer 革命

2017 年 `Attention Is All You Need` 论文提出 Transformer，核心是自注意力机制（Self-Attention）：

| 组件 | 作用 | 公式 |
|------|------|------|
| Scaled Dot-Product Attention | 计算 Query 和 Key 的相似度 | $softmax(QK^T/√d)V$ |
| Multi-Head Attention | 多头并行捕捉不同子空间 | Concat(head₁,...,headₙ)W₀ |
| Positional Encoding | 注入位置信息 | sin/cos 函数或可学习参数 |
| Feed Forward | 非线性变换 | ReLU(W₁x + b₁)W₂ + b₂ |

Transformer 的优势在于可并行计算、全局感受野、长程依赖建模，这使其成为后续 GPT、BERT、T5 等模型的基础架构。

## 预训练大语言模型

### GPT 系列

GPT 采用自回归（Autoregressive）架构，从左到右逐 token 生成。GPT-3（175B 参数）展示了少样本学习（Few-shot Learning）能力。GPT-4 引入多模态理解和推理链（Chain-of-Thought）。

### BERT 与编码器架构

BERT 使用掩码语言模型（Masked LM）和下一句预测（NSP）进行预训练，擅长理解任务（分类、NER、QA）。

### 混合架构

- **T5**：Text-to-Text 统一框架，所有任务映射为文本生成。
- **MoE（Mixture of Experts）**：条件计算，每个 token 只激活部分专家，如 Mixtral 8x7B。
- **Mamba**：状态空间模型（SSM），线性复杂度替代注意力机制，推理速度更快。

### 训练范式演变

| 阶段 | 方法 | 代表模型 | 数据量 |
|------|------|----------|--------|
| 预训练 | 自监督学习（MLM/CLM）| GPT-3、LLaMA | 万亿 token |
| 指令微调 | 监督微调（SFT）| InstructGPT | 万级指令 |
| 偏好对齐 | 强化学习（RLHF/DPO）| GPT-4、Claude | 十万级偏好对 |

## 多模态模型

CLIP 通过对比学习对齐图文向量空间，使得零样本图像分类成为可能。后续 Flamingo、LLaVA 等模型将视觉编码器和大语言模型融合，实现了图文理解、文档分析、图表推理等能力。

当前前沿模型已支持文本、图像、音频、视频的联合理解与生成。
