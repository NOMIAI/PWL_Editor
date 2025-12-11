# PWL波形编辑器 (PWL Editor)

一个基于Python和CustomTkinter的现代PWL（Piecewise Linear）波形编辑器，专为Virtuoso仿真波形设计。
本项目所有内容均为作者0代码使TraeIDE AI开发生成，作者不为任何问题负责。
<img width="1511" height="1038" alt="image" src="https://github.com/user-attachments/assets/0c994cfb-eaae-448c-bea3-558cc33144bc" />

## 功能特点

- **交互式波形编辑**：
  - 拖拽调整波形点（支持X/Y轴锁定）
  - 框选多个点进行批量操作
  - 滚轮缩放与鼠标右键平移视图
- **高精度控制**：
  - 1ps (1e-12s) 最小时间精度
  - 智能防止点重叠（自动推挤/限制）
- **数据管理**：
  - 实时预览PWL文本
  - 一键复制到剪贴板
  - 导入/导出PWL文件
- **现代化界面**：
  - 基于CustomTkinter的暗色主题
  - 高性能Canvas渲染（60FPS流畅体验）

## 快速开始

### 使用便携式版本 (无需安装)
1. 下载最新发布的 `PWL_Editor.exe`。
2. 双击直接运行即可，无需安装Python或任何依赖。
3. 支持Windows 7/10/11。

### 从源码运行
需要安装Python 3.8+（推荐使用 3.11/3.12）。

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 运行程序：
    ```bash
    python pwl_editor.py
    ```
3. 运行测试：
    ```bash
    python -m unittest -q
    ```

### 从源码打包便携式EXE（Windows）
```bash
python build_exe.py
```
生成的可执行文件位于 `dist/PWL_Editor.exe`。

## 操作指南

### 鼠标操作
- **左键单击**：选中单个点
- **左键拖拽**：
  - **空白处拖拽**：框选多个点
  - **点上拖拽**：移动选中的点（自动吸附时间网格）
- **右键拖拽**：平移画布视图
- **滚轮滚动**：
  - **直接滚动**：垂直（Y轴）缩放
  - **按住Ctrl+滚动**：水平（X轴）缩放
- **Ctrl+A**：全选所有点
- **Delete**：删除选中的点

### 键盘快捷键
- **Ctrl+C**：复制当前波形的PWL文本
- **Ctrl+S**：保存PWL文本到文件
- **Ctrl+O**：打开/导入PWL文件

## 更新日志

### v1.0.0 (2025-12-07)
- **初始正式发布**
- 移除Matplotlib依赖，改用原生Canvas实现高性能渲染
- 实现智能拖拽逻辑：
  - 拖拽释放后执行最小时间间隔限制（1ps）
  - 拖拽过程中允许自由移动，避免"挤压"邻近点
- 优化坐标轴逻辑：
  - 默认X轴范围0s-1ms
  - 负轴限制为视图的5%
- 增强选择功能：
  - 支持框选后保持选中状态
  - 支持多点同时拖拽

## 快速波形生成
- 支持三种波形：正弦、方波、三角波
- 频率/周期任选：除频率(Hz)外，亦可直接设置周期(s)
- 占空比与时间：
  - 方波可用占空比(%)或高电平时间(s)设置占空
  - 三角波可用上升占比(%)或上升时间(s)设置斜率
- 其它参数：幅度、偏置、持续时长、每周期点数(正弦)、上升/下降时间(方波)

## 技术栈
- Python 3
- CustomTkinter (UI框架)
- Pyperclip (剪贴板交互)
- PyInstaller (打包工具)
 - Pillow (图像处理：头像与图标加载)

## 性能优化摘要
- 取消首次自动缩放，首点放置后视图不跳变。
- 折线分段绘制，在 ps 级缩放下线段保持可见。
- 网格刻度缓存，减少重复计算提高重绘效率。

## CI/CD
- 使用 GitHub Actions 自动化：
  - 在 `ubuntu-latest` 上运行单元测试
  - 在 `windows-latest` 上构建便携式 `PWL_Editor.exe` 并作为构建产物上传

## 许可证
本项目采用 MIT 许可证，详见 `LICENSE` 文件。
