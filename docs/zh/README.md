# EasyRemote 中文文档中心

Author: Silan Hu (silan.hu@u.nus.edu)

## 推荐阅读顺序

1. [快速开始](user-guide/quick-start.md)
2. [安装指南](user-guide/installation.md)
3. [API 参考](user-guide/api-reference.md)
4. [核心示例](user-guide/examples.md)
5. [基础教程](tutorials/basic-usage.md)
6. [高级场景](tutorials/advanced-scenarios.md)
7. [部署指南](tutorials/deployment.md)
8. [业务落地与路线分层](CORE_USE_CASES_AND_ROUTES.md)
9. [Killer Apps Gallery](../../gallery/README.md)
10. [Gallery 项目模板](../../gallery/projects/README.md)

## 文档结构

```text
docs/zh/
├── README.md
├── CORE_USE_CASES_AND_ROUTES.md
├── user-guide/
│   ├── quick-start.md
│   ├── installation.md
│   ├── api-reference.md
│   └── examples.md
├── tutorials/
│   ├── basic-usage.md
│   ├── advanced-scenarios.md
│   └── deployment.md
└── research/
    └── whitepaper.md
```

## 说明

- 文档中“当前支持”仅记录代码已实现能力。
- 文档中“未来支持”统一标记为 Roadmap，不与现状混写。
- 核心协议能力请结合测试文件 `tests/test_protocol_adapters.py` 一起阅读。
- 业务场景栏目请看 `gallery/README.md` 与 `gallery/killer_apps.md`。
- 快速上手项目请看 `gallery/projects/README.md`。
