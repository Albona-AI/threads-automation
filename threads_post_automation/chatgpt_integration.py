"""
OpenAI APIを使用して投稿の分析とテンプレート化を行うモジュール
"""

import os
import logging
import openai
from dotenv import load_dotenv
from tqdm import tqdm
from prompt_templates import COMBINED_PROMPT, FINAL_POST_PROMPT
import concurrent.futures
from functools import partial

# .envファイルから環境変数をロード
load_dotenv()
        
# APIキー設定
openai.api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "o1")

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 並行処理の設定
MAX_WORKERS = int(os.getenv("MAX_API_WORKERS", "5"))  # デフォルトは5つの並行ワーカー

def call_openai_api(messages, custom_model=None):
    """
    OpenAI APIを呼び出す関数
    """
    try:
        # グローバル変数のmodelを使用、またはカスタムモデルがあればそれを使用
        use_model = custom_model if custom_model else model
        
        # 使用するモデル名をログに出力
        logger.info(f"使用するOpenAIモデル: {use_model}")
        
        # 新世代モデル（o1/o3など）と従来モデルで分岐
        if "o1" in use_model or "o3" in use_model:
            # 新世代モデル用のパラメータ
            logger.info("新世代モデル用パラメータを使用: max_completion_tokens")
            response = openai.ChatCompletion.create(
                model=use_model,
                messages=messages,
                max_completion_tokens=4000
                # 新世代モデルはtemperatureをサポートしていない
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
        return None

def analyze_and_template_post(post_text, post_username=""):
    """
    投稿を分析しテンプレート化する関数（旧analyze_postとcreate_templateを統合）
    
    Args:
        post_text (str): 分析する投稿テキスト
        post_username (str): 投稿者名
        
    Returns:
        str: 分析結果とテンプレート化されたテキスト
    """
    logger.info(f"Analyzing and templating post from {post_username if post_username else 'anonymous'}")
    
    # プロンプトを作成
    prompt = COMBINED_PROMPT.format(post_text=post_text)
    
    # OpenAI APIを呼び出す
    combined_result = call_openai_api([{"role": "user", "content": prompt}])
    
    if combined_result:
        logger.info("投稿分析・テンプレート化が完了しました")
        return combined_result
    else:
        logger.error("投稿分析・テンプレート化に失敗しました")
        return None

def generate_final_post(template, target, username):
    """
    テンプレートとターゲットから最終的な投稿を生成する関数
    
    Args:
        template: テンプレート
        target: ターゲット名
        username: 元の投稿者名
        
    Returns:
        str: 生成された最終投稿
    """
    try:
        # ターゲットと投稿者名をログに記録
        logger.info(f"Generating final post for target '{target}' based on {username}'s template")
        
        # フォーマットの前にデバッグロギングを追加
        logger.debug(f"Template data type: {type(template)}")
        logger.debug(f"Target data type: {type(target)}")
        
        # テンプレートとターゲットが文字列であることを確認
        template_str = str(template) if template is not None else ""
        target_str = str(target) if target is not None else ""
        
        # プロンプトを作成
        prompt = FINAL_POST_PROMPT.format(template=template_str, target=target_str)
        
        # APIを呼び出す
        messages = [{"role": "user", "content": prompt}]
        final_post = call_openai_api(messages)
        
        return final_post
    except Exception as e:
        logger.error(f"Final post generation error: {e}")
        return None

def _process_post(post, targets):
    """
    単一の投稿を処理するヘルパー関数
    
    Args:
        post: (username, post_text, _) のタプル
        targets: ターゲット名のリスト
        
    Returns:
        list: (username, target, final_post) のタプルのリスト
    """
    username, post_text, _ = post
    results = []
    
    # 投稿分析・テンプレート化（統合版）
    combined_result = analyze_and_template_post(post_text, username)
    if not combined_result:
        logger.warning(f"Skipping post from {username} due to analysis/template failure")
        return results
    
    # 各ターゲット向けに並行して最終投稿を生成
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 部分関数を作成して投稿者名とテンプレートを固定
        gen_post_for_target = partial(
            _generate_post_for_target, 
            template=combined_result, 
            username=username
        )
        
        # 並行してターゲットごとの投稿を生成
        for target, final_post in zip(targets, executor.map(gen_post_for_target, targets)):
            if final_post:
                results.append((username, target, final_post))
            else:
                logger.warning(f"Failed to generate post for {username} targeting {target}")
    
    return results

def _generate_post_for_target(target, template, username):
    """
    特定のターゲット向けに投稿を生成するヘルパー関数
    
    Args:
        target: ターゲット名
        template: テンプレート
        username: 投稿者名
        
    Returns:
        str: 生成された投稿、または失敗した場合はNone
    """
    return generate_final_post(template, target, username)

def process_posts(posts, targets):
    """
    収集した投稿を処理し、各ターゲット向けの最終投稿を生成する関数
    
    Args:
        posts (list): (username, post_text) のタプルのリスト
        targets (list): ターゲット名のリスト
        
    Returns:
        list: (参考投稿名, ターゲット名, 完成した投稿本文) のタプルのリスト
    """
    final_posts = []
    
    logger.info(f"Processing {len(posts)} posts for {len(targets)} targets")
    
    # 投稿ごとに並行して処理
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 部分関数を作成してターゲットリストを固定
        process_single_post = partial(_process_post, targets=targets)
        
        # 進捗バーを表示しながら処理
        results_iter = executor.map(process_single_post, posts)
        for post_results in tqdm(results_iter, total=len(posts), desc="Processing posts"):
            final_posts.extend(post_results)
    
    logger.info(f"Generated a total of {len(final_posts)} final posts")
    return final_posts