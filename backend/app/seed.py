import json
from datetime import datetime, timezone
from app.db import connection
from app.security import hash_password

PRODUCTS = [
    (
        "P001",
        "静音降噪耳机 H1",
        "audio",
        "通勤、工作与旅途，让声音回到你自己。",
        29900,
        24,
        "headphones",
        {
            "降噪": "主动降噪 ANC",
            "续航": "30 小时",
            "连接": "蓝牙 5.3",
            "重量": "245 g",
        },
    ),
    (
        "P002",
        "机械键盘 K8",
        "workspace",
        "紧凑布局和柔和手感，把每一次输入变成享受。",
        45900,
        18,
        "keyboard",
        {
            "布局": "87 键",
            "轴体": "热插拔茶轴",
            "连接": "USB-C / 蓝牙",
            "兼容": "Windows / macOS",
        },
    ),
    (
        "P003",
        "无线充电板 Q15",
        "charging",
        "桌面少一根线，日常多一点从容。",
        8900,
        40,
        "charger",
        {
            "功率": "15 W",
            "协议": "Qi 无线充电",
            "接口": "USB-C",
            "保护": "过温 / 异物检测",
        },
    ),
    (
        "P004",
        "便携音箱 S2",
        "audio",
        "从书桌到野餐，好声音随身同行。",
        19900,
        16,
        "speaker",
        {"续航": "12 小时", "防水": "IPX7", "连接": "蓝牙 5.3", "重量": "360 g"},
    ),
    (
        "P005",
        "人体工学鼠标 M3",
        "workspace",
        "自然握持，安静点击，陪伴长时间创作。",
        16900,
        25,
        "mouse",
        {"连接": "2.4G / 蓝牙", "DPI": "800–3200", "按键": "静音微动", "续航": "60 天"},
    ),
    (
        "P006",
        "桌面扩展坞 D7",
        "charging",
        "一个接口，连接你的整张工作台。",
        23900,
        12,
        "hub",
        {
            "接口": "7 合 1",
            "视频": "HDMI 4K 60 Hz",
            "供电": "PD 100 W",
            "数据": "USB 3.0",
        },
    ),
]

DOCS = [
    (
        "returns",
        "退货政策",
        "收货后7天内可申请无理由退货，商品需保持原状、配件及包装完整。质量问题由店铺承担运费，个人原因由买家承担。退款在退货验收后3到5个工作日原路返回。",
    ),
    (
        "shipping",
        "配送与运费",
        "订单满99元包邮，不足99元收取8元运费。支付后通常48小时内发货，标准配送3到5个工作日，偏远地区7到10个工作日。订单页显示当前配送状态。",
    ),
    (
        "warranty",
        "保修与维修",
        "耳机、键盘、音箱、鼠标、扩展坞提供12个月质保，无线充电板提供6个月质保。非人为故障免费维修或更换，人为损坏提供有偿维修。",
    ),
    (
        "payment",
        "支付与发票",
        "本项目使用模拟支付，不扣款、不连接支付机构。模拟支付后订单进入待发货状态。电子发票在真实业务中需支付成功后申请，本演示不提供真实发票。",
    ),
    (
        "cancellation",
        "取消订单",
        "仅待支付订单可取消，取消后释放预留库存。已支付订单请申请售后，不支持直接取消。重复取消不会重复增加库存。",
    ),
    (
        "privacy",
        "账户与订单隐私",
        "订单和售后工单仅向当前登录用户及店铺管理员开放。客服只能查询当前用户订单，无法查询其他用户数据。请勿在聊天中发送密码或支付信息。",
    ),
    (
        "confirmation",
        "AI 操作确认",
        "AI 可查询商品、订单和政策。添加购物车、取消订单及创建售后工单时先生成确认卡片，用户确认后才执行。确认卡有效期10分钟。AI不能执行支付或退款。",
    ),
    (
        "headphones",
        "H1 耳机说明",
        "H1静音降噪耳机售价299元，主动降噪ANC，蓝牙5.3，续航30小时，适合通勤和办公室。不支持游泳佩戴。质保12个月。",
    ),
    (
        "keyboard",
        "K8 键盘说明",
        "K8机械键盘售价459元，87键紧凑布局、热插拔茶轴，支持USB-C和蓝牙，兼容Windows与macOS，适合办公和编程。质保12个月。",
    ),
    (
        "charger",
        "Q15 充电板说明",
        "Q15无线充电板售价89元，支持Qi协议15W充电，USB-C供电，带过温与异物检测。手机需支持Qi协议，建议取下厚金属保护壳。质保6个月。",
    ),
    (
        "speaker",
        "S2 音箱说明",
        "S2便携音箱售价199元，蓝牙5.3，续航12小时，IPX7防水，重量360克，适合户外和野餐。质保12个月。",
    ),
    (
        "mouse",
        "M3 鼠标说明",
        "M3人体工学鼠标售价169元，支持2.4G和蓝牙双模，800到3200DPI，静音按键，续航60天。适合办公使用。质保12个月。",
    ),
    (
        "hub",
        "D7 扩展坞说明",
        "D7桌面扩展坞售价239元，7合1接口，HDMI支持4K 60Hz，PD供电100W，USB3.0。笔记本USB-C接口需支持视频输出才能连接显示器。质保12个月。",
    ),
]


def seed():
    now = datetime.now(timezone.utc).isoformat()
    with connection(write=True) as conn:
        for uid, email, name, role in [
            ("demo-user", "demo@shop.local", "林同学", "customer"),
            ("demo-admin", "admin@shop.local", "店铺管理员", "admin"),
        ]:
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
                conn.execute(
                    "INSERT INTO users VALUES (?,?,?,?,?)",
                    (uid, email, name, hash_password("Demo12345!"), role),
                )
        for pid, name, category, description, price, stock, image, specs in PRODUCTS:
            if not conn.execute(
                "SELECT id FROM products WHERE id=?", (pid,)
            ).fetchone():
                conn.execute(
                    "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,1)",
                    (
                        pid,
                        name,
                        category,
                        description,
                        price,
                        stock,
                        image,
                        json.dumps(specs, ensure_ascii=False),
                    ),
                )
        for doc in DOCS:
            if not conn.execute(
                "SELECT id FROM knowledge WHERE id=?", (doc[0],)
            ).fetchone():
                conn.execute("INSERT INTO knowledge VALUES (?,?,?)", doc)
        if not conn.execute(
            "SELECT 1 FROM orders WHERE id=?", ("ORD-DEMO",)
        ).fetchone():
            conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
                (
                    "ORD-DEMO",
                    "demo-user",
                    "shipped",
                    29900,
                    "上海市 · 演示收货地址",
                    now,
                    "seed-order",
                ),
            )
            conn.execute(
                "INSERT INTO order_items VALUES (?,?,?,?,?)",
                ("ORD-DEMO", "P001", "静音降噪耳机 H1", 29900, 1),
            )
        if not conn.execute(
            "SELECT id FROM fulfillment_events WHERE order_id=?", ("ORD-DEMO",)
        ).fetchone():
            conn.execute(
                "INSERT INTO fulfillment_events VALUES (?,?,?,?,?)",
                (
                    "FUL-DEMO",
                    "ORD-DEMO",
                    "shipped",
                    "模拟物流：上海仓已出库，等待配送更新",
                    now,
                ),
            )
