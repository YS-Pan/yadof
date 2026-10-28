# Windows HTCondor：当前 FRP / CCB 配置脚本

这是一套独立脚本，不依赖或修改 `../htcondor_config/` 中的脚本。
适用于**已有 HTCondor、FRP 隧道及池认证凭据**的 Windows 节点。
脚本配置 HTCondor，不安装或重写 frpc/frps，不生成、分发或显示 token/密钥。

## 当前连接方式（2026-09-28 只读核查）

| 项目 | 观测值 |
| --- | --- |
| 当前 Worker | `DESKTOP-B407` |
| 管理机 / trust domain | `DESKTOP-A2092` |
| Worker 上的 FRP visitor | `127.0.0.1:29618` |
| 管理机实际 Collector | `192.168.137.1:9618`，发布名称 `DESKTOP-A2092:9618` |
| Worker 的 `CCB_ADDRESS` | `127.0.0.1:29618` |
| Worker 的 `OUTBOUND_CCB_ADDRESS` | `127.0.0.1:29618` |
| Worker 的 `USE_OUTBOUND_CCB` | `False` |
| 管理机的 `CCB_OUTBOUND_PROXY` | `True` |
| 管理机的 `CCB_OUTBOUND_TARGET_ALLOWLIST` | `192.168.137.1` |
| 管理机的 `CCB_SERVER_STREAMING` | `True` |
| 本机 HTCondor | `25.14.1` |

这些 CCB 值已从**运行中的守护进程**读取，不只是配置文件中的文字。
本机的实时机器广告带有 `CCBID`；MasterLog 也记录了注入 CCB 地址。
`USE_OUTBOUND_CCB=False` 表示不在本机自动启动内嵌 Collector/CCB，
不代表未使用远端 CCB。其他局域网节点的广告不一定有 `CCBID`。

核查时 SharedPortLog 持续记录向管理机 `192.168.137.1:9618` 的反向连接失败。
因此“Collector 中看得见节点”不能证明作业匹配、文件传输、执行和回传均正常。
本套脚本尚未用于重配真实集群，也不宣称修复了该现存通路故障。

## 运行前提

- Windows PowerShell 5.1、HTCondor **25.14.1 或更新版本**，以及名为 `condor` 的 Windows 服务。
  这里使用当前版本的 outbound CCB / streaming 功能；不要套用旧版普通 CCB 的假设。
- Worker 的本地 FRP visitor 已运行，并确实转发到该池的 Collector。
  默认读取已有 loopback 端口，未配置时采用 `29618`；不是 frps 的公网控制端口。
- 管理机上的 FRP 代理已能访问本机 Collector 的 shared port（默认 `9618`）。
  本脚本不新增对公网或所有网卡放行的防火墙规则。
- 已有可用的 IDTOKENS/NTSSPI/PASSWORD 等认证配置和对应 `ALLOW_*` / `DENY_*` 授权。
  trust domain 必须与现有凭据所属池一致；仅填写名称不能产生信任关系。
  脚本保留已有认证方法、凭据目录与授权规则，并强制默认认证、加密和完整性检查为 `Required`。
- 应用配置会停止/重启 HTCondor，可能终止正在执行的作业。请在维护时操作。

Worker 不需要通过 DNS 直接连接管理机名称；它连接本地 FRP visitor。
管理机名称用于记录身份，`TRUST_DOMAIN` 单独保留。管理机脚本则要求所填名称解析到本机。

## 四个入口

**双击对应 `.cmd`，不是 `.ps1`。** `.cmd` 用 Windows PowerShell 启动同名脚本；
需要时弹出 UAC，并保留窗口显示输入、错误及结果。所有文件应放在同一个目录。

| 入口 | 功能 |
| --- | --- |
| `1_htcondor_leave_all_pools.cmd` | 确认 `LEAVE` 后停止并禁用 Condor 服务，清空此套配置的入池/CCB/flocking 设置；保留 FRP 和凭据。不是日常配置必跑步骤。 |
| `2_htcondor_register_manager.cmd` | 配置 Collector、Negotiator、Schedd 和 outbound CCB broker；已有显式声明的执行资源会保留。 |
| `3_htcondor_register_worker.cmd` | 通过本地 FRP visitor 注册 Worker。首次迁移/注册且没有显式资源声明时，只运行 MASTER，不启动 STARTD，不接任务。 |
| `4_htcondor_set_execute_resources.cmd` | 保持 Manager/Worker 角色及 FRP 配置，设置执行目录、CPU、内存和磁盘后启用 STARTD。 |

新管理机：`2 → 4`（只有需要执行任务时才运行 4）。
新工作机：`3 → 4`。已有当前 FRP Worker 可直接运行 **4** 迁移并明确声明资源。
重复运行 2/3 会保留此套或旧套中完整、有效的显式资源声明，不会取消管理机的执行功能。

CPU 为逻辑处理器数；内存为 MiB；磁盘输入为 MiB、写入 Condor 时转换为 KiB。
它们是调度资源声明，不是 OS 级别的硬限额。请为 Windows 和日常工作预留资源。
执行目录默认沿用当前 `EXECUTE`，无值时使用安装目录下的 `execute`。
不默认要求 R: 盘；拒绝盘符根目录、UNC/映射盘、链接/联接路径及受保护目录。
目录会授予 SYSTEM/Administrators 完全控制和本地 Users 修改权限，供 slot 用户使用。

## 先预览

在本目录的 PowerShell 中：

```powershell
# 只读现有配置，生成并用本机 HTCondor 解析器验证预览。
.\3_htcondor_register_worker.ps1 -DryRun -OutputDirectory D:\yadof\temp\frp-preview

# 资源数值仅为示例，按各机器实际用途填写。
.\4_htcondor_set_execute_resources.ps1 -DryRun `
    -ExecuteDirectory D:\condor\execute -Cpus 2 -MemoryMiB 4096 -DiskMiB 8192 `
    -OutputDirectory D:\yadof\temp\frp-preview
```

`-DryRun` 不要求管理员权限，也不提权，不访问远程 Collector。
它只读取本机配置/硬件并在输出目录创建预览，不改变服务、正式配置、ACL 或防火墙。
预览目录包含独立配置、可解析的临时根配置和拟写入的正式根配置。
默认预览目录在 `%TEMP%\yadof-htcondor-frp`；仓库内验证应显式使用根 `temp/`。
HTCondor 的 `LOCAL_CONFIG_FILE` 不识别 shell 引号；脚本对含空格的路径使用 Windows 短路径。
如果该卷禁用了短名称且无法取得无空格路径，会在应用前报错；请选择无空格的安装/输出路径。

## 命令行应用示例

以下命令会重启服务；`-Yes` 明确接受该中断，`-NonInteractive` 禁止交互提问。
未带 `-Yes` 的交互运行会要求输入 `APPLY` 或 `LEAVE`。

```powershell
# 在 DESKTOP-A2092 上，沿用当前管理机地址与 outbound CCB 目标范围。
.\2_htcondor_register_manager.ps1 -ManagerName DESKTOP-A2092 `
    -TrustDomain DESKTOP-A2092 -BrokerTargetAllowlist 192.168.137.1 `
    -NonInteractive -Yes -NoPause

# 在远端工作机上；不同机器的 visitor 端口可以不同。
.\3_htcondor_register_worker.ps1 -ManagerName DESKTOP-A2092 `
    -TrustDomain DESKTOP-A2092 -VisitorPort 29618 -NonInteractive -Yes -NoPause

.\4_htcondor_set_execute_resources.ps1 -ExecuteDirectory D:\condor\execute `
    -Cpus 2 -MemoryMiB 4096 -DiskMiB 8192 -NonInteractive -Yes -NoPause
```

可选参数：

- `-SharedPort`：本机 Condor 监听端口，默认沿用当前设置或 `9618`。不能与 Worker visitor 端口相同。
- `-PrivateNetworkName`：默认沿用当前值或本机名称；互不直通的站点不要填写同一个名字。
- `-NetworkAdapterName`：可选的本机网卡名称；未指定时保留当前 `NETWORK_INTERFACE`（当前为 `*`）。
  `BIND_ALL_INTERFACES=True` 保持当前路由方式，选择网卡并不构成访问限制。
- `-EnableSubmit`：Worker 同时启用本地 SCHEDD。已有本地提交能力也会保留。
  增加提交节点还须核对凭据、授权及 broker 目标范围，不能仅靠此开关保证跨站作业成功。
- `-RootConfig`：指定实际根配置。应用后会查询运行中的 daemon 核对，防止只改到未被服务使用的文件。
- `-BrokerTargetAllowlist`：管理机允许 outbound CCB 代理拨号的目标，默认沿用本机现值或公布地址。
  当前池仅放行 `192.168.137.1`；不要不加区分地改成 `*`。

## 写入、验证和恢复

正式覆盖文件为根配置同目录的 `condor_config.yadof_frp`。
根配置末尾增加带标记的 `LOCAL_CONFIG_FILE` 扩展项，让它在已有 local 文件之后加载。
原 `condor_config.local`、其中旧 FRP 块及其他配置文件不被编辑或删除。
新覆盖文件完整指定角色、Collector、双向 CCB、执行开关和安全默认值，避免旧角色字段混用。
如其他配置/用户环境最终覆盖了计划值，预检会失败，不继续应用。

应用前在根配置旁的 `yadof_frp_backups\时间戳\` 保存原根配置、原覆盖文件（如有）、
服务状态和已有执行目录的 ACL。该目录不放进 `LOCAL_CONFIG_DIR`，避免备份被误加载。
服务停下后写入配置，验证生效值，再启动并检查运行中的 MASTER/STARTD 配置和
**本次重启产生的新广告**；Worker 执行广告还须带 `CCBID`，不能用陈旧的节点记录判成功。

应用失败时自动尝试恢复上述配置、已有目录的 ACL、服务启动类型及运行状态。
新建的执行目录和预览会保留，不递归删除目录。回滚失败会明确打印备份路径。
手工恢复时先停止服务，根据 `state.json` 将 `condor_config.original` 复制回 `RootConfig`，
有旧覆盖文件则复制回；原本不存在则只移除新建的覆盖文件，然后恢复原服务状态。

配置应用和注册成功后，仍需另行进行一个小型作业的提交、传输、执行、回传验收。
这些脚本不会自动提交测试作业，也不会重置现有 FRP 连接。

## 离线回归检查与参考

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\test_offline.ps1 `
    -OutputDirectory D:\yadof\temp\frp-regression
```

测试使用临时配置以及替代的服务控制函数；不会停止实际服务或修改实际 Condor 配置。

参考（核对日期 2026-09-28）：

- [HTCondor networking / CCB tunneling](https://htcondor.readthedocs.io/en/25.x/admin-manual/networking.html)
- [配置文件加载顺序](https://htcondor.readthedocs.io/en/25.x/admin-manual/configuration/global.html#LOCAL_CONFIG_FILE)
- [HTCondor security](https://htcondor.readthedocs.io/en/25.x/admin-manual/security.html)
- [condor_config_val](https://htcondor.readthedocs.io/en/25.x/man-pages/condor_config_val.html)
