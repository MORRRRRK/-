from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ... import VERSION_LABEL
from ..widgets import make_button

CHANGELOG = """V2.5
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
        update_row.addWidget(self.check_update_button)
        update_row.addWidget(self.update_status, 1)
        layout.addLayout(update_row)

    def _check(self) -> None:
        self.update_status.setText("正在检查更新…")
        self.on_check_update(self)

    def refresh(self) -> None:
        pass
