自动化的配置job需要的资源数量。

当前的distributed job需要的资源是由用户手动填写的。
在config.py里有：
```
HTCONDOR_REQUEST_CPUS = 4
HTCONDOR_REQUEST_MEMORY = "8GB"
HTCONDOR_REQUEST_DISK = "5GB"
```
我希望将它改成自动化的。

具体有：
1. 首先运行smoke test，此时使用某个默认的资源需求量。
2. 运行时记录实际使用的资源量，放到metadata里，回传回来。
3. 根据回传的实际使用量，修改config.py里的需求量。对于memory和disk，应该乘一个系数，比如2。
4. 开始第一代仿真，用上述的实际使用量（乘系数）作为htcondor里申请的资源量。每个仿真也记录实际使用量。
5. 下一代的申请量，基于上一代的实际使用量。用去掉使用量最多的10%的结果后的最大值（第90%大的实际使用量）乘以一个系数，比如1.5。之后的每代都如此往复。

新建一个文件来放这些功能的代码。
