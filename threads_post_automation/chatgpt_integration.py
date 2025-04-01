"""
OpenAI APIを使用して投稿の分析とテンプレート化を行うモジュール
"""

import os
import logging
import openai
from dotenv import load_dotenv
from tqdm import tqdm
from prompt_templates import ANALYSIS_PROMPT, TEMPLATE_PROMPT, FINAL_POST_PROMPT

# .envファイルから環境変数をロード
load_dotenv()

# APIキー設定
openai.api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def call_openai_api(messages, model="gpt-4-turbo"):
    """
    OpenAI APIを呼び出す関数
    """
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            max_completion_tokens=4000,
            temperature=0.7
        )
        return response.choices[0].message["content"]
    except Exception as e:
        logger.error(f"OpenAI API呼び出しエラー: {e}")
        return None

def analyze_post(post_text, post_username=""):
    """
    投稿を分析する関数
    
    Args:
        post_text (str): 分析する投稿テキスト
        post_username (str): 投稿者名
        
    Returns:
        str: 分析結果テキスト
    """
    logger.info(f"Analyzing post from {post_username if post_username else 'anonymous'}")
    
    # プロンプトを作成
    prompt = ANALYSIS_PROMPT.format(post_text=post_text)
    
    # OpenAI APIを呼び出す
    analysis_result = call_openai_api([{"role": "user", "content": prompt}])
    
    if analysis_result:
        logger.info("投稿分析が完了しました")
        return analysis_result
    else:
        logger.error("投稿分析に失敗しました")
        return None

def create_template(post_text, analysis_result, post_username=""):
    """
    投稿テンプレートを作成する関数
    
    Args:
        post_text (str): 原文の投稿テキスト
        analysis_result (str): 分析結果テキスト
        post_username (str): 投稿者名
        
    Returns:
        str: テンプレート化したテキスト
    """
    logger.info(f"Creating template for post from {post_username if post_username else 'anonymous'}")
    
    # プロンプトを作成
    prompt = TEMPLATE_PROMPT.format(
        post_text=post_text,
        analysis_result=analysis_result
    )
    
    # OpenAI APIを呼び出す
    template_result = call_openai_api([{"role": "user", "content": prompt}])
    
    if template_result:
        logger.info("テンプレート作成が完了しました")
        return template_result
    else:
        logger.error("テンプレート作成に失敗しました")
        return None

def generate_final_post(template, target, post_username=""):
    """
    最終投稿を生成する関数
    
    Args:
        template (str): 投稿テンプレート
        target (str): ターゲット名
        post_username (str): 元の投稿者名
        
    Returns:
        str: 完成した投稿テキスト
    """
    logger.info(f"Generating final post for target '{target}' based on {post_username if post_username else 'anonymous'}")
    
    # プロンプトを作成
    prompt = FINAL_POST_PROMPT.format(
        target=target,
        template=template
    )
    
    # OpenAI APIを呼び出す
    final_post = call_openai_api([{"role": "user", "content": prompt}])
    
    if final_post:
        logger.info(f"ターゲット '{target}' 向けの投稿生成が完了しました")
        return final_post
    else:
        logger.error(f"ターゲット '{target}' 向けの投稿生成に失敗しました")
        return None

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
    
    for username, post_text, _ in tqdm(posts, desc="Processing posts"):
        # 投稿分析
        analysis_result = analyze_post(post_text, username)
        if not analysis_result:
            logger.warning(f"Skipping post from {username} due to analysis failure")
            continue
        
        # テンプレート作成
        template_result = create_template(post_text, analysis_result, username)
        if not template_result:
            logger.warning(f"Skipping post from {username} due to template creation failure")
            continue
        
        # 各ターゲット向けに最終投稿を生成
        for target in tqdm(targets, desc=f"Generating posts for {username}", leave=False):
            final_post = generate_final_post(template_result, target, username)
            if final_post:
                final_posts.append((username, target, final_post))
            else:
                logger.warning(f"Failed to generate post for {username} targeting {target}")
    
    logger.info(f"Generated a total of {len(final_posts)} final posts")
    return final_posts 