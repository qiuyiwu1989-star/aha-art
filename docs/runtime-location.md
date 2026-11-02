# AHA 运行位置只读核验 · 2026-10-26

## 已确认

- 公网入口122.51.221.171，SSH别名deepbrain。
- AHA Nginx站点include的zao122-cutover-proxy.conf，将请求送127.0.0.1:18772；该端口监听者是sshd，不是AHA应用进程。
- 该隧道SSH连接来源180.165.55.201；对应已接受会话的密钥标签为zao122-w-cutover-20260727。未读取或输出私钥。
- 122具有wg-ai内网路由：10.255.122.1→10.255.122.2；WireGuard peer endpoint同为180.165.55.201。由此将运行侧定位到AI中台网络，但同公网地址不能独立证明两个连接一定在同一物理主机。
- 10.255.122.2:22返回Ubuntu OpenSSH banner；已配置身份访问被publickey拒绝。未尝试密码、修改密钥或访问控制。80超时，已有配置指向的18199当前拒绝连接。
- 通过18772并指定Host aha.yishujia.art，/museum.html和/cat/healthz均200。首页123109字节，SHA256 f8c9caaeaec8bf90b1efe56c76a64d4cc3076115baeedf029f17ac0fcb1c3aa5，与122的/data/pub/p/aha/museum.html完全一致。
- 122仓库/home/ubuntu/users/qiuyiwu/aha-art/web/museum.html为123063字节、SHA256 c6786e41af183bcd006031780a0a42b90885d7bf9dfbd86b50686f7aa7a81c28，与线上不同。不能从该仓库直接覆盖。

## 尚未确认

AI侧实际hostname、AHA进程/容器、监听端口、工作目录、挂载和当前后端提交。需要AI中台已授权可用的SSH连接身份/管理通道；当前连接不具备该节点登录权限。不能将“入口/镜像在122”误称为“实际应用进程在122”，也不能凭共享公网地址冒称已确认物理主机。

这些查询均为只读；没有修改隧道、Nginx、DNS、部署目录、密钥或生产数据库。

## 2026-10-27 新线索

122的zaocode-ai-chisel-client.service处于active，Description为ZaoCode AI Chisel client to W，配置目标http://w.sitd.site:8091，映射127.0.0.1:18974:127.0.0.1:18199。w.sitd.site解析到180.165.55.201，与AHA反向隧道来源一致；此证据支持同一网络出口，不能单凭DNS断定同一物理主机。公网22端口实测Connection refused。未输出认证参数，未改隧道或访问控制。此前内网10.255.122.2:22可连接但已有身份publickey拒绝。下一步需该运行网络现有管理方式，而非122登录信息。

## 用户纠正 · 2026-10-27

用户明确指出w.sitd.site与其无关。撤回将该域名作为AHA管理目标的推断，不再对该域名尝试管理访问。现有隧道配置与共享公网地址不足以确认AHA实际部署主机。重新核验正式域名HTTP200，healthz ok/works208855，122的aha-catalog及aha-gen仍inactive，AHA站点仍include反向代理配置，18772由sshd监听。实际上游管理位置仍未知。
