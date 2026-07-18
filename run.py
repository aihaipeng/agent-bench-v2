"""Agent Bench Web 服务入口。"""

import uvicorn


def main() -> None:
    """启动 Agent Bench Web 服务。"""
    uvicorn.run("web.app:app", host="127.0.0.1", port=8010, reload=True)


if __name__ == "__main__":
    main()
