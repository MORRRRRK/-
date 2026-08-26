from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ... import VERSION_LABEL, __version__
from ...core import repository
from ...edition import is_customer
from ...services.release import DEFAULT_CODE_REPO, DEFAULT_REPO
from ..release_worker import ReleasePushWorker
from ..widgets import make_button

CHANGELOG = """V4.2
· 新增账户管理：现金/银行卡/支付宝/微信/信用卡/贷款等，自动汇总总资产、总负债、净资产
· 新增日常逐笔记账：支出/收入/转账、分类、账户、商家、备注、可报销
· 持仓管理新增交易历史：买入/卖出/分红/定投/赎回，按 FIFO 计算成本与收益
· 局域网新增 PWA 手机记账页：手机浏览器可查看和快速记账
· 新增历史数据迁移工具，旧大笔消费自动迁移为交易记录

V4.1
· 新增 V4 手机互联：桌面与手机通过同步服务双向互通
· 手机端新增工资管理、资产规划、智能报告
· 手机端登录一次长期有效，仅清除缓存或退出登录后需重新登录
· 桌面与手机版本统一为 V4.1，更新说明随服务端同步

V3.5.1
· 持仓管理新增“净值”栏：股票/ETF/基金/黄金实时价格与净值直接展示，无价格时按持仓市值÷份额回填
· 开发版补全“查看公式”：持仓总持仓/累计收益/收益率、资产总览、年度汇总、资产规划均增加公式说明
· 一键推送集成源码上传：构建客户版时同步提交并推送源码到 GitHub 源码仓库
· 设置新增“V4 手机互联（服务器同步）”：桌面与手机通过服务端双向同步

V3.5
· 所有可保存模块增加独立保存按钮：工资详情、N险N金、专项附加扣除、设置各模块分开保存
· 开支管理：月度流水取消年终奖、各类补贴、报销、水电列，水电改为每月支出，删除下方月支出模块
· 工资管理：自动计算结果与全年个税汇总合并，删除全年个人五险一金行
· 持仓管理：删除“执行今日定投”按钮，启动与定时刷新时按定投策略自动执行；更新时间精确到分钟
· 持仓管理：无代码黄金账户更名为黄金账户；缺失代码会明确报错
· 资产规划：退休金测算移动到工资管理
· 全局删除仅需一次确认，不再提示撤销
· 开发版“关于”页新增“推送客户版更新”按钮，可一键打包并发布到 GitHub

V3.4
· “月度流水”改名“开支管理”，新增“月支出”模块按月汇总日常消费，年度汇总同步变更
· 工资详情改为“13薪 xN”“年终奖 xN”，新增/删除/撤销按钮移到各自模块标题旁
· 专项附加扣除地区选择合并为一行，其余扣除项目按两行四列紧凑排列
· 取消独立的“税后工资计算”，功能合并进“全年个税汇总”
· 修复场外基金实时行情：自动补 .OF 代码；股票类型误标 6 位基金代码时按名称自动修正

V3.3.1
· 修复在线更新卡在 100%：更新前备份数据库不再被未提交事务阻塞，改用独立数据库连接
· 更新下载完成后明确显示“正在校验更新包并备份数据”
· 更新准备阶段发生其他异常时不再静默卡住，会提示错误并写入 update_error.log

V3.3
· 工资参数与税务管理合并为“工资管理”
· 工资详情重做：基本工资、13薪xN、年终奖xN、自定义绩效/补贴，支持按月/季/年发放
· N险N金：表格放大并完整展示，保留自定义新增、删除、撤销
· 专项附加扣除：租房按省-市-区逐级选择，自动带出扣除档位
· 开发版计算结果旁新增“查看公式”，客户版不显示
· 全年个税汇总与逐月累计预扣预缴表合并展示，年终奖计税方式保留

V3.2
· 工资参数新增专项附加扣除：租房城市、赡养老人、子女教育、婴幼儿照护、继续教育、房贷、大病医疗
· 工资参数新增税后工资模拟：全年个税、年终奖单独/并入计税、12 个月税后收入
· 新增“税务管理”页：按实际月度流水累计预扣预缴，逐月展示累计应税所得与当月个税
· 月度流水新增“月消费”，联动年度汇总与资产总览消费统计

V3.1.3
· 修复坚果云中文目录同步 404：目录自动创建且正确处理编码
· 更新下载新增全局进度窗口，不再只在“关于”页显示
· 防火墙按钮改为隐藏终端窗口并等待管理员确认

V3.1.2
· 修复 WebDAV 深层目录同步 404，自动创建坚果云目录
· 设置页改为可滚动，窗口缩小时不再挤压
· 更新下载新增进度条，并加强网络超时保护
· 设置页新增“开放防火墙”按钮，解决手机无法访问局域网 Web
· 输入框内容不再被页面刷新覆盖

V3.1.1
· 修复 WebDAV 测试连接误报：改用标准 PROPFIND 探测，坚果云兼容性更好

V3.1
· 新增加密云同步：数据库加密后上传到 WebDAV（坚果云/Nextcloud/NAS）
· 支持手动同步、从云端恢复、启动时自动同步
· 云端只保存加密文件，同步密码不进入发布包
· 同步前自动备份本地数据库，冲突时保留云端旧文件副本

V3.0
· 新增智能报告：接入 OpenAI 兼容大模型，可生成年度/月度/持仓/自定义报告
· 报告支持 Markdown 预览、复制、导出，生成记录保存在本地数据库
· 新增局域网只读 Web 端：手机/浏览器通过访问码查看总览、流水、持仓和报告
· 设置新增大模型接口与局域网访问配置，不包含任何隐私数据外传承诺

V2.5
· 资产规划新增退休金测算：按省份 2024 计发基数估算，支持多段工作经历
· 每段工作单独计算，以最新一份工作为准；可保存工作记录、撤销删除
· 可从工资参数一键填充养老缴费基数与个人比例
· 开发版更新支持私有 GitHub 仓库 Token，设置中填写后即可在线更新
· 客户版支持软件内直接更新，不再需要重新下载安装程序

V2.4
· 客户版在线更新：启动检查 + 手动检查，GitHub Releases 分发
· 更新前自动备份数据库，更新只替换程序文件，数据不丢失

V2.3
· 月度流水移除图片按钮，保留双击预览，12 个月完整展示且取消滚动
· 修复月度流水加载慢：批量填充表格并只计算一次行高
· 全局删除确认提示与“撤销删除”保持一致
· 下拉菜单重新设计样式，浅色/深色主题适配
· 修复易方达全球成长精选等老基金刷新报 1002，自动走东财净值兜底

V2.2
· 资产总览图表改为原位更新，不再重复创建控件，生成更快
· 汇总明细直接全部显示，不显示内部滚动条
· 月度流水全部展示，禁用所有单元格鼠标滚轮改值
· 修复月度流水撤销删除，撤销后自动定位到恢复的记录
· 持仓解析/实时行情/定投使用同花顺 API 实测通过
· 老基金代码增加东财兜底解析与净值

V2.1
· 设置新增清除缓存、自定义导出与备份目录
· 所有删除操作增加二次确认，并支持撤销误删
· 资产总览图表改为缓存复用并关闭动画，生成更快
· 月度流水、持仓管理、工资参数、资产规划整页滚动
· 持仓管理改为表格直接编辑 + 右上角保存，下拉可自定义，数值直接填写
· 定投按交易日自动执行并计入持仓与收益
· 新增无代码黄金账户模块，接入新浪实时金价参考
· 所有表格点击整行高亮

V2.0
· 接入同花顺金融数据 API，持仓管理可刷新实时行情
· 资产总览图表支持悬停显示数值，图表放大并开启抗锯齿
· 保存成功时按钮变绿提示
· 设置新增深色 / 浅色 / 跟随系统主题

V1.2
· 侧边栏新增“关于”，主菜单只保留“文件”
· 资产总览图表改为上下排列，修复按月汇总年份选择问题
· 月度流水备注自动换行，大笔消费/收入改为日期与金额范围筛选
· 工资参数支持分险种填写基数、自定义新增险种（六险二金）
· 表格与界面圆角美化

V1.1
· 更换财务管理风格图标
· 菜单整合：备份/恢复/导出/导入移入“文件”
· 新增“设置”：字体大小、主题色
· 资产总览支持按年/按月汇总
· 月度流水支持图片备注与预览、金额直接输入
· 修复大笔消费/收入类型筛选问题
· 持仓管理支持渠道筛选

V1.0
· 月度流水、工资参数、持仓管理、资产总览、资产规划
· 数据保存在程序目录 data/finance.db，可整目录迁移"""


class AboutPage(QWidget):
    def __init__(self, conn, on_check_update):
        super().__init__()
        self.conn = conn
        self.on_check_update = on_check_update
        self._release_worker: ReleasePushWorker | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel(f"个人财务软件 {VERSION_LABEL}")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        info = QLabel(
            "本地单机版个人财务软件，数据保存在程序目录 data/finance.db，"
            "整个程序文件夹可复制到其他 Windows 10/11 x64 电脑继续使用。"
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        info.setObjectName("fieldLabel")
        layout.addWidget(info)

        changelog = QLabel(CHANGELOG)
        changelog.setObjectName("card")
        changelog.setWordWrap(True)
        changelog.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        changelog.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(changelog, 1)

        update_row = QHBoxLayout()
        self.check_update_button = make_button("检查更新", primary=True)
        self.check_update_button.clicked.connect(self._check)
        self.update_status = QLabel("")
        self.update_status.setObjectName("fieldLabel")
        self.push_update_button = make_button("推送客户版更新")
        self.push_update_button.clicked.connect(self._push_customer_update)
        self.push_update_button.setVisible(not is_customer())
        update_row.addWidget(self.check_update_button)
        update_row.addWidget(self.push_update_button)
        update_row.addWidget(self.update_status, 1)
        layout.addLayout(update_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def _check(self) -> None:
        self.update_status.setText("正在检查更新…")
        self.on_check_update(self)

    def _push_customer_update(self) -> None:
        if self._release_worker is not None and self._release_worker.isRunning():
            return
        if (
            QMessageBox.question(
                self,
                "确认推送",
                "将自动构建客户版、打包、上传源码并发布到 GitHub，"
                "整个过程需要几分钟。是否继续？",
            )
            != QMessageBox.Yes
        ):
            return
        version, ok = QInputDialog.getText(
            self, "推送客户版更新", "版本号（如 3.6.0）：", text=__version__
        )
        if not ok or not version.strip():
            return
        version = version.strip().lstrip("v")
        notes, ok = QInputDialog.getMultiLineText(
            self,
            "推送客户版更新",
            "本次更新说明：",
            f"V{version}：",
        )
        if not ok:
            return
        repo = repository.get_setting(self.conn, "update_repo", "").strip()
        code_repo = repository.get_setting(
            self.conn, "code_repo", DEFAULT_CODE_REPO
        ).strip() or DEFAULT_CODE_REPO
        token = repository.get_setting(self.conn, "github_token", "").strip()
        if not repo:
            repo = DEFAULT_REPO
        if not token:
            QMessageBox.warning(
                self,
                "无法推送",
                "未填写 GitHub Token，请先在“设置”的常用设置中填写。",
            )
            return
        self._release_worker = ReleasePushWorker(
            version,
            repo,
            token,
            notes.strip(),
            code_repo=code_repo,
            parent=self,
        )
        self._release_worker.finished.connect(self._on_release_finished)
        self._release_worker.failed.connect(self._on_release_failed)
        self.update_status.setText("正在构建客户版、上传源码并推送更新…")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self._release_worker.start()

    def _on_release_finished(self, url: str) -> None:
        self._release_worker = None
        self.clear_progress()
        self.update_status.setText("已推送，客户版可检查更新")
        QMessageBox.information(self, "推送完成", f"客户版更新已发布：\n{url}")

    def _on_release_failed(self, message: str) -> None:
        self._release_worker = None
        self.clear_progress()
        self.update_status.setText("推送失败")
        QMessageBox.warning(self, "推送失败", message)

    def refresh(self) -> None:
        pass

    def set_progress(self, current: int, total: int) -> None:
        if total <= 0:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setVisible(True)
            self.update_status.setText("正在校验更新包并备份数据…")
            return
        percent = max(0, min(100, int(current * 100 / total)))
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(percent)
        self.progress_bar.setVisible(True)
        self.update_status.setText(f"正在下载并校验更新包… {percent}%")

    def clear_progress(self) -> None:
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
