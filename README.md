# football-ai-engine

简单的足球比赛预测演示仓库（Streamlit 前端 + 简易规则引擎 + XGBoost 示例）。

## 目录结构（简要）
- app.py         # Streamlit 前端，展示 predictions.json 中的结果
- main.py        # 抓取 API 数据并生成 predictions.json（示例）
- predict.py     # 用 pandas+xgboost 训练并生成 predictions.json（示例）
- requirements.txt

## 快速开始（本地）
1. 克隆仓库
   git clone https://github.com/bily1258-design/football-ai-engine.git
   cd football-ai-engine

2. 建议先创建并激活虚拟环境（示例：venv）
   python -m venv .venv
   source .venv/bin/activate   # macOS/Linux
   .venv\Scripts\activate      # Windows

3. 安装依赖
   pip install -r requirements.txt

4. 设置环境变量（如果使用 main.py 抓取在线 API）
   export FOOTBALL_API_KEY="your_api_key_here"   # macOS/Linux
   set FOOTBALL_API_KEY="your_api_key_here"      # Windows CMD
   $Env:FOOTBALL_API_KEY="your_api_key_here"     # PowerShell

   注意：main.py 中使用的是 football-data.org 的 API，请根据该服务的文档获取正确 API Key 和 endpoint。

5. 生成预测（任选其一）
   - 使用 rules/engine（main.py）抓取并生成文件：
     python main.py

   - 或运行示例模型训练并生成 predictions.json（predict.py）：
     python predict.py

6. 启动前端（Streamlit）
   streamlit run app.py

默认情况下 app.py 会读取仓库根目录下的 `predictions.json` 并展示其中的记录。

## 说明与建议
- 已统一前端读取 `predictions.json`，确保 main.py/predict.py 写出该文件以便前端展示。
- 请在生产或公开仓库中：
  - 不把密钥写入代码库；使用环境变量或 CI secret。
  - 给依赖指定精确版本并使用 lock 文件以保证可复现。
  - 增加测试和 CI（建议添加 GitHub Actions 做 lint 和 basic tests）。

## 许可
请在此处添加 LICENSE（当前仓库没有 LICENSE，请根据需要添加）。