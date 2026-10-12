"""幂等初始化本地商店、知识库和演示账户。"""

from app.db import initialize

if __name__ == "__main__":
    initialize()
    print("初始化完成！")
