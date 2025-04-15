"""
OpenAI API接続のテスト用スクリプト
"""

import os
import logging
import openai
from dotenv import load_dotenv

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# .envファイルから環境変数をロード
load_dotenv()

# APIキー設定
openai.api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "gpt-4.1-2025-04-14")

def call_openai_api(messages, custom_model=None):
    """
    OpenAI APIを呼び出す関数
    """
    try:
        # グローバル変数のmodelを使用、またはカスタムモデルがあればそれを使用
        use_model = custom_model if custom_model else model
        
        # 使用するモデル名をログに出力
        logger.info(f"使用するOpenAIモデル: {use_model}")
        
        # 新世代モデルの識別
        new_gen_models = ["o1", "o3", "gpt-4o", "gpt-4-1106-preview", "gpt-4.1"]
        is_new_gen = any(model_id in use_model for model_id in new_gen_models)
        
        if is_new_gen:
            # 新世代モデル用のパラメータ
            logger.info("新世代モデル用パラメータを使用: max_completion_tokens")
            response = openai.ChatCompletion.create(
                model=use_model,
                messages=messages,
                max_completion_tokens=4000
            )
        else:
            # 従来のモデル用のパラメータ
            logger.info("従来モデル用パラメータを使用: max_tokens, temperature")
            response = openai.ChatCompletion.create(
                model=use_model,
                messages=messages,
                max_tokens=4000,
                temperature=0.7
            )
        
        return response.choices[0].message["content"]
    except Exception as e:
        logger.error(f"OpenAI API呼び出しエラー: {e}")
        logger.error(f"エラー詳細: {str(e)}")
        return None

def test_api():
    """
    APIの動作をテストする関数
    """
    logger.info("APIテスト開始")
    
    # テスト用のプロンプト
    test_prompt = "Threadsに投稿するための短い文章を日本語で1つ書いてください。"
    
    # APIを呼び出す
    response = call_openai_api([{"role": "user", "content": test_prompt}])
    
    if response:
        logger.info("APIテスト成功！")
        logger.info(f"レスポンス:\n{response}")
    else:
        logger.error("APIテスト失敗")

if __name__ == "__main__":
    test_api() 