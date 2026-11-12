# 集群配置界面

Windows 双击根目录的 `admin_config.pyw`，或在 MSI 安装后的开始菜单打开
**Yadof Cluster Configuration**。需要 Python 3.11+、Tk、psutil 和单独安装的
HTCondor；FRP 模式还需要 frpc ≥ 0.64。窗口启动时请求管理员权限。
管理员入口及其代码随 MSI、管理员 ZIP 分发，不属于 pip wheel 的用户命令。

上方显示 HTCondor 根配置、本机监听端口和连接方式。切换标签页只切换表单，实际
连接方式由上方“局域网 / FRP / STCP”决定。点击“保存并应用”前不会改配置。
应用会重启服务，可能中断本机作业。

- **本机资源**：选择 manager、submit 或 worker。manager 运行 Collector、Negotiator、
  Schedd；submit 运行 Schedd；worker 执行任务。manager / submit 可另外启用执行资源。
  声明 CPU、内存 MiB、磁盘 MiB，选择本地固定磁盘上的非根 EXECUTE 工作目录。
  数值不能超过逻辑 CPU、物理内存和磁盘可用空间；这些是调度资源声明。
  超时驱逐按本次作业的 `JobCurrentStartDate` 计算。启用时覆盖本机运行超时策略，
  禁用时关闭 `PREEMPT` 和 `STARTD.PREEMPT`。提交端是否重试作业由提交设置决定。
- **局域网设置**：选择本机网卡的 IPv4。其他节点填写 Manager 主机名/IP 和端口；
  manager 使用本机网卡及上方端口。沿用现有 HTCondor 认证、授权配置；管理员应预先
  为各节点设置一致的认证与信任策略。工具不修改防火墙。
- **FRP设置**：选择 frpc.exe，填写 VPS 和 server port。认证支持 token 文件或输入
  token；文件写为原生 `auth.tokenSource`，不会同时写 `auth.token`。
  添加本机 STCP proxies 及指向其他机器的 visitors；secretKey 以掩码显示。
  proxy localPort 必须等于本机 HTCondor 端口；localIP / bindAddr 固定 127.0.0.1。
  submit / worker 必须指定指向 Manager 的 visitor 名称。

双向路由要求各节点使用相同私网名称。visitor 的 serverName、secretKey 必须匹配
对端 proxy，bindPort 必须等于对端 HTCondor 监听端口。各节点监听端口应在 STCP
集群内唯一；本机 visitor 端口不能重复，也不能与自己的 HTCondor 端口冲突。
例如 manager 监听 9618、worker 监听 25564：manager 的 visitor 绑定 25564 指向 worker，
worker 的 visitor 绑定 9618 指向 manager。更多节点须配置相应回访路径。
本机校验不能证明对端密钥、VPS 或跨机文件传输正常，需要两端完成设置后验证。

可从现有 STCP TOML 导入；保存时生成独立的 `%PROGRAMDATA%\Yadof\frpc.toml`。
导入范围是本界面支持的服务器、token、proxy、visitor 字段；其他 FRP 调优字段不会
复制。含其他隧道类型或非回环监听的文件会拒绝导入。导入不会停止旧 frpc，应用前
应停用重复隧道，避免端口或代理名称冲突。配置由 `Yadof-frpc` 计划任务以 SYSTEM
身份运行并在开机时启动；token 文件必须对该身份可读。VPS 上的 frps 独立维护。

资源表显示 Name、Activity、任务编号 GlobalJobId、Cpus、Memory(MB)、Disk(MB)、
CpusUsage 和广告地址，不显示 Machine。Disk 从 KiB 转为 MiB。表格和本机广告地址
每 10 秒刷新；地址可选中复制。Collector 不可达时仍显示本机地址，并清空过期表格。

“退出所有集群”停止并禁用本机 HTCondor，清空 Collector、flocking、CCB 和私网连接，
禁用 Yadof 管理的 FRP 计划任务。不操作远端集群或其他软件管理的 frpc。

界面状态独立存放在 `%PROGRAMDATA%\Yadof\admin_config.json`，不重复存 token 或
STCP 密钥；密钥由原生 frpc TOML 保存。该目录及备份仅限当前管理员、Administrators
和 SYSTEM 访问。不要将本机运行文件提交到 Git。

应用前用 `condor_config_val` 和 `frpc verify` 校验暂存文件；原生配置和服务/任务状态
备份到 `backups/时间戳/`。普通 local 文件按加载顺序合并到根文件旁的
`condor_config.local`，根文件只加载这一份 local。旧文件保留但停止加载；无法安全
整理的动态 include 会拒绝应用。清理已加载配置中的旧 `YADOF_*` 项及属性列表引用，
保留其他原生设置（例如 HFSS 线程环境变量）。不会新增仅供 Yadof 读取的原生配置项。
清理支持反斜杠续行及续行之间的注释，普通文件名和引号中的文字不会被当成旧属性。
若自定义表达式仍引用旧宏或 ClassAd 属性，保存前会显示配置文件路径、行号、配置项及
被引用的旧名称；按提示修改该表达式后再保存。错误信息不显示配置值。
启动失败时恢复原文件和服务/任务状态；执行目录及其授权保留，避免自动删除任务数据。
错误信息会标明回滚是否完整和备份位置。

离线验收，不修改现有集群：

```powershell
python -m pytest admin_tool/cluster_config/test_config.py -q -o addopts= --basetemp=temp/admin-tests
python admin_config.pyw --smoke-test
```

原生参数参考：[HTCondor 网络](https://htcondor.readthedocs.io/en/25.0/admin-manual/networking.html)、
[FRP STCP](https://gofrp.org/en/docs/examples/stcp/)、
[FRP token 文件](https://gofrp.org/en/docs/features/common/authentication/)。
