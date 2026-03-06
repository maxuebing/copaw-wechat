from setuptools import setup, find_packages

setup(
    name="copaw-plugin-wechat",
    version="0.1.0",
    description="WeChat (WeCom) plugin for CoPaw",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=[
        "wechatpy>=1.8.0",
        "requests>=2.25.0",
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "cryptography>=3.4.0",
        "pydantic>=1.8.0"
    ],
    python_requires=">=3.8",
)
