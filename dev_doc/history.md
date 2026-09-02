# yadof 简史

本文按主要版本概括 yadof 的发展历程，记录各阶段最重要的功能和代码组织变化。
逐次改动的详细记录见 [change_records/](change_records/)。

## 0.1.0：基础功能

实现了基础优化功能。此时尚未形成独立的 package，通用代码基础设施与每次优化任务
使用的代码放在同一个文件夹中。

## 0.2.0：package 与 workspace 分离

形成可安装的 package，将每次优化时不需要修改的通用代码收进 package。开始新任务时
先建立 workspace，将本次工作需要编写或调整的代码放在其中。

## 0.3.0：local 与 fast mode

添加了 local mode 和 fast mode，扩展了任务的执行方式。local mode 在本机运行准备好的
任务；fast mode 提供更轻量的本地评估路径。

## 0.4.0：优化与代理模型模块化

形成 `optimize` 和 `surrogate` 模块，明确优化流程与代理模型的职责，使二者可以更灵活地
组合和扩展。

## 0.5.0：优化流程可编程

进一步发展了灵活的 `optimization.py`，由用户用 Python 显式编排优化流程。流程中可以
插入任意任务所需的代码，按需要组织数据处理、候选选择、评估与代理模型训练等步骤。
