# ... existing code ...
import time
import random
import json
import os
import re
import datetime
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import logging
import sys
from dotenv import load_dotenv  # python-dotenv パッケージが必要です
import urllib.parse

# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ThreadsScraper:
    def __init__(self, headless=False):
        """
        Threadsスクレイパーの初期化
        
        Args:
            headless (bool): ヘッドレスモードで実行するかどうか。デフォルトはFalse（画面表示あり）
        """
        options = webdriver.ChromeOptions()
        
        # 一般的なブラウザに見せるユーザーエージェントの設定
        user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        options.add_argument(f'user-agent={user_agent}')
        
        if headless:
            options.add_argument('--headless=new')
        
        # 自動化検出の無効化を試みる
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # プロキシ検出を無効化
        options.add_argument('--disable-proxy-client-detection')
        
        # クッキーを維持
        options.add_argument('--enable-cookies')
        
        # 追加の引数
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--lang=ja-JP,ja')
        
        self.driver = webdriver.Chrome(options=options)
        
        # ウィンドウサイズを設定（モバイルではなくデスクトップサイズ）
        self.driver.set_window_size(1280, 800)
        
        # 自動化スクリプトの検出を避けるためにステルスJSを実行
        self.driver.execute_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        """)
        
        # Cookieの保存パス
        self.cookies_file = 'threads_cookies.json'
        
        # ドライバーの初期化後に追加
        self.logged_in = False
    
    def _human_like_delay(self, min_sec=1.0, max_sec=3.5):
        """
        人間らしい遅延をシミュレート
        
        Args:
            min_sec (float): 最小遅延時間（秒）
            max_sec (float): 最大遅延時間（秒）
        """
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
    
    def _scroll_with_strategy(self, strategy="normal", iterations=5, scroll_amount=300):
        """
        様々なスクロール戦略を1つの関数に統合
        
        Args:
            strategy (str): スクロール戦略 ("normal", "deep", "human", "progressive", "bottom")
            iterations (int): スクロール回数
            scroll_amount (int): 基本スクロール量
            
        Returns:
            bool: 新しいコンテンツが読み込まれたかどうか
        """
        logger.info(f"Scrolling with {strategy} strategy for {iterations} iterations")
        new_content_loaded = False
        
        # 初期要素数を記録
        initial_elements = len(self.driver.find_elements(By.CSS_SELECTOR, "article"))
        
        if strategy == "bottom":
            # 最下部へのスクロール
            for i in range(iterations):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                logger.info(f"Bottom scroll {i+1}/{iterations}")
                self._human_like_delay(2.0, 3.0)
                
                # フィードの終わりをチェック
                if self._check_end_of_feed():
                    logger.info("Reached end of feed")
                    break
        
        elif strategy == "deep":
            # 深いスクロール
            for i in range(iterations):
                logger.info(f"Deep scroll iteration {i+1}/{iterations}")
                
                # 現在表示中の最後の投稿要素までスクロール
                try:
                    articles = self.driver.find_elements(By.CSS_SELECTOR, "article")
                    if articles:
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'end'});", 
                                                  articles[-1])
                        self._human_like_delay(1.0, 2.0)
                        self.driver.execute_script("window.scrollBy({top: 1000, behavior: 'smooth'});")
                except Exception as e:
                    logger.warning(f"Error scrolling to last article: {e}")
                
                self._human_like_delay(4.0, 6.0)
        
        elif strategy == "human":
            # 人間らしいスクロール
            for _ in range(iterations):
                # ランダムなスクロール
                scroll_distance = random.randint(400, 800)
                before_height = self.driver.execute_script("return document.body.scrollHeight")
                
                # ランダムな速度でスクロール
                scroll_behavior = random.choice(["auto", "smooth"])
                self.driver.execute_script(f"window.scrollBy({{top: {scroll_distance}, behavior: '{scroll_behavior}'}});")
                
                self._human_like_delay(1.5, 3.0)
                
                after_height = self.driver.execute_script("return document.body.scrollHeight")
                if after_height > before_height:
                    new_content_loaded = True
                    
                # 時々少し戻る（より人間らしく）
                if random.random() < 0.15:
                    self.driver.execute_script(f"window.scrollBy({{top: {-random.randint(50, 100)}, behavior: 'auto'}});")
                    self._human_like_delay(0.5, 1.0)
        
        elif strategy == "progressive":
            # 段階的スクロール
            for i in range(iterations):
                window_height = self.driver.execute_script("return window.innerHeight")
                scroll_amount = int(window_height * 0.8)
                
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                logger.info(f"Progressive scroll #{i+1}: scrolled {scroll_amount}px")
                
                self._human_like_delay(2.0, 3.0)
                
                # 時々一時停止
                if i % 5 == 4:
                    pause_time = random.uniform(1.5, 3.0)
                    time.sleep(pause_time)
                    
                    # 上下の微調整
                    self.driver.execute_script("window.scrollBy(0, -200);")
                    time.sleep(0.8)
                    self.driver.execute_script("window.scrollBy(0, 250);")
                    time.sleep(1.0)
        
        else:  # normal
            # 通常のスクロール
            for i in range(iterations):
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                self._human_like_delay(1.0, 2.0)
        
        # 最終的な要素数をチェック
        final_elements = len(self.driver.find_elements(By.CSS_SELECTOR, "article"))
        elements_added = final_elements - initial_elements
        
        logger.info(f"Scroll complete: {elements_added} new elements loaded (total: {final_elements})")
        
        return elements_added > 0 or new_content_loaded
    
    def _safe_scroll(self, scroll_amount=300):
        """
        安全なスクロール方法（JavaScriptを使用）- 改良版
        
        Args:
            scroll_amount (int): スクロール量（ピクセル）
        
        Returns:
            tuple: (スクロール前の高さ, スクロール後の高さ)
        """
        try:
            # スクロール前の要素数を記録
            before_elements = len(self.driver.find_elements(By.CSS_SELECTOR, "article"))
            
            # スクロール前の高さを取得
            before_height = self.driver.execute_script("return document.body.scrollHeight")
            
            # ランダムな速度でスクロールを実行（より人間らしく）
            scroll_behavior = random.choice(["auto", "smooth"])
            self.driver.execute_script(f"window.scrollBy({{top: {scroll_amount}, behavior: '{scroll_behavior}'}});")
            
            # 適切な待機（スクロール後のコンテンツ読み込みを待つ）
            self._human_like_delay(2.0, 3.5)  # 待機時間を延長
            
            # スクロール後の高さを取得
            after_height = self.driver.execute_script("return document.body.scrollHeight")
            
            # スクロール後の要素数を確認
            after_elements = len(self.driver.find_elements(By.CSS_SELECTOR, "article"))
            
            logger.info(f"Scrolled {scroll_amount}px: Elements before={before_elements}, after={after_elements}")
            logger.info(f"Page height: before={before_height}, after={after_height}")
            
            return (before_height, after_height)
        except Exception as e:
            logger.warning(f"Error during scroll: {e}")
            return (0, 0)
    
    def _deep_scroll(self, iterations=5):
        """
        より深くスクロールして新しいコンテンツを読み込む（改良版）
        
        Args:
            iterations (int): スクロールする回数
        
        Returns:
            bool: 新しいコンテンツが読み込まれたかどうか
        """
        new_content_loaded = False
        last_element_count = len(self.driver.find_elements(By.CSS_SELECTOR, "article"))
        
        for i in range(iterations):
            logger.info(f"Deep scroll iteration {i+1}/{iterations}")
            
            # 現在表示中の最後の投稿要素までスクロール
            try:
                articles = self.driver.find_elements(By.CSS_SELECTOR, "article")
                if articles:
                    # 最後の投稿まで強制的にスクロール
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'end'});", articles[-1])
                    logger.info(f"Scrolled to the last article of {len(articles)} articles")
                    
                    # 画面の少し下までさらにスクロール（新しいコンテンツのトリガー）
                    self.driver.execute_script("window.scrollBy({top: 1000, behavior: 'smooth'});")
            except Exception as e:
                logger.warning(f"Error scrolling to last article: {e}")
            
            # ロード完了を待機（長めに設定）
            self._human_like_delay(6.0, 8.0)
            
            # 新しいコンテンツが読み込まれたか確認
            current_elements = len(self.driver.find_elements(By.CSS_SELECTOR, "article"))
            if current_elements > last_element_count:
                new_content_loaded = True
                logger.info(f"New content loaded! Articles: {last_element_count} -> {current_elements}")
                last_element_count = current_elements
            else:
                logger.warning(f"No new articles loaded during deep scroll iteration {i+1}")
                # 追加のランダムスクロールで読み込みをトリガー
                random_scroll = random.randint(800, 1500)
                self.driver.execute_script(f"window.scrollBy({{top: {random_scroll}, behavior: 'auto'}});")
                self._human_like_delay(3.0, 5.0)
                
                # ページを少し上に戻してから再度下にスクロール（読み込みのトリガーに効果的）
                self.driver.execute_script("window.scrollBy({top: -300, behavior: 'auto'});")
                self._human_like_delay(1.0, 2.0)
                self.driver.execute_script("window.scrollBy({top: 700, behavior: 'smooth'});")
                self._human_like_delay(3.0, 5.0)
        
        return new_content_loaded
    
    def _human_like_scroll(self, scroll_count=10):  # スクロール回数を増やす
        """
        人間らしいスクロール動作をシミュレート（修正版）
        
        Args:
            scroll_count (int): スクロールする回数
        
        Returns:
            bool: 新しいコンテンツが読み込まれたかどうか
        """
        new_content_loaded = False
        
        for _ in range(scroll_count):
            # スクロール距離をランダム化
            scroll_distance = random.randint(500, 900)  # スクロール距離を増やす
            
            # JavaScriptでスクロール実行
            before_height, after_height = self._safe_scroll(scroll_distance)
            
            # 高さが変わった場合は新しいコンテンツが読み込まれた
            if after_height > before_height:
                new_content_loaded = True
                logger.info(f"Page height increased from {before_height} to {after_height}")
            
            # スクロール後の一時停止
            self._human_like_delay(2.0, 4.0)  # 待機時間を増やす
            
            # 約10%の確率で少し戻る
            if random.random() < 0.10:
                back_scroll = random.randint(-100, -50)
                self._safe_scroll(back_scroll)
                self._human_like_delay(0.8, 1.5)
                
                # 元の方向に戻る
                self._safe_scroll(abs(back_scroll) * random.uniform(0.7, 0.9))
                self._human_like_delay(0.5, 1.0)
        
        return new_content_loaded
    
    def _wait_for_content_load(self, timeout=10):
        """
        コンテンツ読み込みを待機するヘルパーメソッド
        
        Args:
            timeout (int): 最大待機時間（秒）
            
        Returns:
            bool: コンテンツが読み込まれたかどうか
        """
        try:
            # 何らかのコンテンツ要素が表示されるのを待つ
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "article"))
            )
            logger.info("コンテンツが読み込まれました")
            return True
        except Exception as e:
            logger.warning(f"コンテンツ読み込み待機中にタイムアウトまたはエラー: {e}")
            return False
    
    def _safe_click(self, element):
        """
        より安全なクリック方法
        
        Args:
            element: クリックする要素
        """
        try:
            # まず要素が表示されているか確認
            if not element.is_displayed():
                # 見えるようにスクロール
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                self._human_like_delay(0.5, 1.0)
            
            # クリック方法をランダムに選択（検出回避のため）
            click_method = random.choice([1, 2, 3])
            
            if click_method == 1:
                # 通常のクリック
                element.click()
                logger.info("Normal click")
            elif click_method == 2:
                # JavaScriptでクリック
                self.driver.execute_script("arguments[0].click();", element)
                logger.info("JavaScript click")
            else:
                # ActionChainsでクリック
                ActionChains(self.driver).move_to_element(element).click().perform()
                logger.info("ActionChains click")
            
            self._human_like_delay(0.8, 1.5)
            return True
        except Exception as e:
            logger.warning(f"Safe click failed: {e}")
            # 最終手段としてJavaScriptクリック
            try:
                self.driver.execute_script("arguments[0].click();", element)
                logger.info("Fallback JavaScript click")
                self._human_like_delay(0.8, 1.5)
                return True
            except:
                logger.error("All click methods failed")
                return False
    
    def _human_like_mouse_movement(self, element=None):
        """
        人間らしいマウス移動をシミュレートする
        
        Args:
            element: 移動先の要素（Noneの場合はランダムな移動）
        """
        try:
            # ActionChainsを初期化
            actions = ActionChains(self.driver)
            
            # 現在のスクリーン位置を取得
            screen_width = self.driver.execute_script("return window.innerWidth;")
            screen_height = self.driver.execute_script("return window.innerHeight;")
            
            # 現在のマウス位置を推定（ブラウザの中央と仮定）
            current_x = screen_width // 2
            current_y = screen_height // 2
            
            if element:
                # 要素が指定されている場合はその位置を取得
                target_x = element.location['x'] + (element.size['width'] // 2)
                target_y = element.location['y'] + (element.size['height'] // 2)
            else:
                # ランダムな位置に移動
                target_x = random.randint(10, screen_width - 10)
                target_y = random.randint(10, screen_height - 10)
            
            # 0から1の範囲でいくつかのランダムな点を生成（ベジェ曲線のコントロールポイント）
            points = []
            num_points = random.randint(3, 6)  # コントロールポイントの数
            
            for _ in range(num_points):
                # ランダムなコントロールポイントを生成
                px = random.uniform(0, 1)
                py = random.uniform(0, 1)
                points.append((px, py))
            
            # 点を時間順にソート
            points.sort(key=lambda p: p[0])
            
            # 最初と最後の点を固定
            points[0] = (0, 0)
            points[-1] = (1, 1)
            
            # 自然なマウス動作をシミュレートするためのステップ数
            steps = random.randint(25, 50)
            
            for i in range(steps):
                # 各ステップでの進行度（0から1）
                t = i / (steps - 1)
                
                # ベジェ曲線に基づく位置を計算
                # 単純な実装: 線形補間を使用
                x = current_x
                y = current_y
                
                for j in range(len(points) - 1):
                    # 各セグメント間を補間
                    segment_x = current_x + (target_x - current_x) * (points[j][0] * (1 - t) + points[j+1][0] * t)
                    segment_y = current_y + (target_y - current_y) * (points[j][1] * (1 - t) + points[j+1][1] * t)
                    
                    # 各セグメントの重みを計算
                    weight = 1 if j == 0 else 0
                    
                    # 重み付き平均で位置を更新
                    x = x * (1 - weight) + segment_x * weight
                    y = y * (1 - weight) + segment_y * weight
                
                # マウスを計算された位置に移動
                actions.move_by_offset(x - current_x, y - current_y).perform()
                
                # 現在位置を更新
                current_x, current_y = x, y
                
                # ランダムな短い遅延を追加
                time.sleep(random.uniform(0.01, 0.03))
            
            # 目標に到達
            if element:
                # 最終的に要素上にマウスを置く
                actions.move_to_element(element).perform()
            
            return True
        
        except Exception as e:
            logger.warning(f"Mouse movement error: {e}")
            # エラーが発生した場合は通常の移動を試みる
            if element:
                try:
                    ActionChains(self.driver).move_to_element(element).perform()
                    return True
                except:
                    pass
            return False

    def _human_like_typing(self, element, text):
        """
        人間らしいタイピング動作をシミュレート
        
        Args:
            element: テキストを入力する要素
            text (str): 入力するテキスト
        """
        try:
            # 要素が見えるようにスクロール
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            self._human_like_delay(0.5, 1.0)
            
            # 要素をクリック
            self._safe_click(element)
            
            # テキストをクリア
            element.clear()
            self._human_like_delay(0.2, 0.5)
            
            # 文字ごとに遅延をつけてタイピング
            for char in text:
                element.send_keys(char)
                # タイピング速度のばらつきをシミュレート
                typing_delay = random.uniform(0.05, 0.15)
                time.sleep(typing_delay)
            
            # 入力後に少し待機
            self._human_like_delay(0.5, 1.0)
        except Exception as e:
            logger.warning(f"Typing error: {e}")
    
    def save_cookies(self):
        """
        現在のCookieを保存
        """
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f)
            logger.info("Cookies saved successfully")
        except Exception as e:
            logger.warning(f"Error saving cookies: {e}")
    
    def load_cookies(self):
        """
        保存されたCookieをロード
        
        Returns:
            bool: Cookieのロードに成功したかどうか
        """
        if not os.path.exists(self.cookies_file):
            logger.warning("Cookies file not found")
            return False
        
        try:
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
            
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.warning(f"Error adding cookie: {e}")
            
            logger.info("Cookies loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Error loading cookies: {e}")
            return False
    
    def login(self, username, password):
        """
        Threadsにログインする (人間らしい挙動の強化版)
        """
        try:
            # 直接ログインページにアクセス
            self.driver.get("https://www.threads.net/login")
            logger.info("Navigated to direct login URL: https://www.threads.net/login")
            
            # 初期ロード時に長めに待機（5-8秒）
            initial_wait = random.uniform(5.0, 8.0)
            time.sleep(initial_wait)
            logger.info(f"Initial page load wait: {initial_wait:.2f}s")
            
            # ページをわずかにスクロール (ランダムな回数と速度)
            self._random_scrolling(min_scrolls=1, max_scrolls=3)
            
            # ユーザー名入力前に少し待機
            self._human_like_delay(2.0, 4.0)
            
            # ユーザー名入力欄を複数の方法で検索（既存コードは維持）
            username_selectors = [
                "//input[@placeholder='ユーザーネーム、携帯電話番号、またはメールアドレス']",
                "input[autocomplete='username']",
                "input[type='text'][autocapitalize='none']",
                "input[type='text']"
            ]
            
            username_field = None
            for selector in username_selectors:
                try:
                    if selector.startswith("//"):
                        username_field = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                    else:
                        username_field = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    logger.info(f"Username field found with selector: {selector}")
                    break
                except:
                    continue
            
            if not username_field:
                logger.error("Username field not found")
                return False
            
            # ユーザー名入力前に少しスクロール
            self._random_scrolling(min_scrolls=1, max_scrolls=2, pixel_range=(50, 200))
            
            # ユーザー名をゆっくりと1文字ずつ入力
            self._type_like_human(username_field, username)
            logger.info(f"Successfully entered username: {username}")
            
            # 入力後にわずかな時間待機
            self._human_like_delay(1.5, 3.0)
            
            # Tabキーを使ってパスワードフィールドに移動する場合がある
            if random.random() < 0.4:  # 40%の確率でTab使用
                username_field.send_keys(Keys.TAB)
                logger.info("Used TAB key to move to password field")
                self._human_like_delay(0.5, 1.5)
                password_field = self.driver.switch_to.active_element
            else:
                # 既存のパスワードフィールド検出ロジックを使用
                try:
                    password_field = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
                    )
                    logger.info("Password field found")
                except:
                    logger.error("Password field not found")
                    return False
                
                # パスワードフィールドをクリックする前に少し待機
                self._human_like_delay(1.0, 2.5)
                
                # クリック方法をランダムに選択
                click_methods = ["normal", "js", "action_chains"]
                click_method = random.choice(click_methods)
                
                if click_method == "normal":
                    password_field.click()
                    logger.info("Normal click on password field")
                elif click_method == "js":
                    self.driver.execute_script("arguments[0].click();", password_field)
                    logger.info("JavaScript click on password field")
                else:
                    ActionChains(self.driver).move_to_element(password_field).click().perform()
                    logger.info("ActionChains click on password field")
            
            # パスワードをゆっくりと入力
            self._type_like_human(password_field, password)
            logger.info("Password entered successfully")
            
            # 入力後にわずかな時間待機
            self._human_like_delay(2.0, 4.0)
            
            # ログインボタンをクリックする前にページをわずかにスクロール
            self._random_scrolling(min_scrolls=1, max_scrolls=2, pixel_range=(20, 100))
            
            # ログインボタンを見つける
            login_button_selectors = [
                "//div[@role='button']//div[contains(@class, 'xwhw2v2')]",
                "//div[contains(text(), 'ログイン')]",
                "//button[contains(text(), 'ログイン')]",
                "button[type='submit']"
            ]
            
            login_button = None
            for selector in login_button_selectors:
                try:
                    if selector.startswith("//"):
                        login_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        login_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    logger.info(f"Login button found with selector: {selector}")
                    break
                except:
                    continue
            
            if not login_button:
                logger.error("Login button not found")
                return False
            
            # ログインボタンクリック前に待機
            self._human_like_delay(1.5, 3.0)
            
            # クリック方法をランダムに選択
            click_methods = ["normal", "js", "action_chains"]
            click_method = random.choice(click_methods)
            
            if click_method == "normal":
                login_button.click()
                logger.info("Normal click on login button")
            elif click_method == "js":
                self.driver.execute_script("arguments[0].click();", login_button)
                logger.info("JavaScript click on login button")
            else:
                ActionChains(self.driver).move_to_element(login_button).click().perform()
                logger.info("ActionChains click on login button")
            
            logger.info("Login button clicked")
            
            # ログインプロセス後に十分な時間待機
            time.sleep(random.uniform(12.0, 15.0))
            
            # ログイン成功を確認
            current_url = self.driver.current_url
            if "login" in current_url.lower():
                logger.warning(f"Still on login page after login attempt: {current_url}")
                return False
            
            logger.info(f"Login successful, redirected to: {current_url}")
            return True
            
        except Exception as e:
            logger.error(f"Login failed with error: {e}")
            return False

    def _type_like_human(self, element, text):
        """
        人間のようにテキストを入力する関数
        """
        for char in text:
            element.send_keys(char)
            # 文字ごとにランダムな待機時間（より自然な入力速度）
            time.sleep(random.uniform(0.05, 0.25))
        
        # 入力完了後に少し待機
        time.sleep(random.uniform(0.3, 0.7))

    def _random_scrolling(self, min_scrolls=1, max_scrolls=3, pixel_range=(100, 300)):
        """
        ランダムなスクロールを行う関数
        """
        num_scrolls = random.randint(min_scrolls, max_scrolls)
        
        for _ in range(num_scrolls):
            # スクロール量をランダムに決定
            scroll_amount = random.randint(pixel_range[0], pixel_range[1])
            
            # 上下どちらにスクロールするかランダムに決定（75%の確率で下方向）
            if random.random() < 0.75:
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            else:
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")
            
            # スクロール後に待機
            time.sleep(random.uniform(0.3, 1.2))
        
        logger.info(f"Performed {num_scrolls} random scrolls")

    def navigate_to_threads(self):
        """
        Threadsのホームページに移動する
        """
        try:
            # すでにログイン済みで適切なページにいる場合はスキップ
            current_url = self.driver.current_url
            if self.logged_in and "threads.net" in current_url and "login" not in current_url:
                logger.info(f"Already on Threads page: {current_url}")
                return True
            
            logger.info("Navigating to threads.net homepage...")
            self.driver.get("https://www.threads.net")
            self._wait_for_page_load()
            
            # ホームページにアクセスした後のURLを確認
            current_url = self.driver.current_url
            logger.info(f"Current URL after navigation: {current_url}")
            
            # ログインが必要な場合の処理
            if "login" in current_url:
                logger.warning("Redirected to login page - not logged in")
                return False
            
            # ホームページへのナビゲーション成功
            logger.info("Successfully navigated to timeline")
            
            # ページが完全に読み込まれるのを待つ
            logger.info("Waiting for page to fully load...")
            if self._wait_for_content_load():
                return True
            else:
                logger.warning("Page loaded but content might not be fully available")
                return False
        except Exception as e:
            logger.error(f"Error navigating to Threads: {e}")
            return False
    
    def _is_ui_element_text(self, text):
        """
        テキストがUI要素（いいね、返信など）かどうかを判定
        
        Args:
            text (str): 判定するテキスト
        
        Returns:
            bool: UI要素の場合True、そうでなければFalse
        """
        # Threadsの主なUI要素テキスト（日本語と英語）
        ui_texts = [
            'いいね', '返信', '再投稿', 'シェア', 'フォロー', 'フォローする', 'もっと見る',
            'Like', 'Reply', 'Repost', 'Share', 'Follow', 'More',
            '分', '時間', '秒', '日', '分前', '時間前', '秒前', '日前',
            'min', 'hour', 'sec', 'day', 'ago'
        ]
        
        # 長さが極端に短いテキストはUI要素の可能性が高い
        if len(text) < 5:
            return True
        
        # 数字のみ、または数字とカンマだけのテキストはいいね数やカウンターの可能性
        if re.match(r'^\d+(\,\d+)*$', text) or re.match(r'^\d+[kK]$|^\d+\.\d+[kK]$', text):
            return True
        
        # UI要素のテキストが含まれている場合
        for ui_text in ui_texts:
            if ui_text in text:
                return True
        
        # 時間表示パターン
        time_patterns = [
            r'^\d+分$', r'^\d+時間$', r'^\d+日$', r'^\d+秒$',
            r'^\d+分前$', r'^\d+時間前$', r'^\d+日前$', r'^\d+秒前$',
            r'^\d+\s*min(s)?$', r'^\d+\s*hour(s)?$', r'^\d+\s*day(s)?$', r'^\d+\s*sec(s)?$',
            r'^\d+\s*min(s)?\s*ago$', r'^\d+\s*hour(s)?\s*ago$', r'^\d+\s*day(s)?\s*ago$', r'^\d+\s*sec(s)?\s*ago$'
        ]
        
        for pattern in time_patterns:
            if re.match(pattern, text):
                return True
        
        return False
    
    def _force_scroll_to_bottom(self):
        """
        ページの最下部まで強制的にスクロールするメソッド
        """
        try:
            # JavaScriptを使用してページの最下部までスクロール
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            logger.info("ページの最下部まで強制スクロール実行")
            
            # 少し待機して読み込みを待つ
            time.sleep(3)
            
            return True
        except Exception as e:
            logger.warning(f"強制スクロール中にエラー: {e}")
            return False

    def _check_end_of_feed(self):
        """
        フィードの終わりに達したかどうかをチェックするメソッド
        
        Returns:
            bool: フィードの終わりに達したかどうか
        """
        try:
            # フィードの終わりを示す要素を探す (「これ以上の投稿はありません」などのテキスト)
            end_texts = ["これ以上の投稿はありません", "No more posts", "End of feed"]
            
            for text in end_texts:
                # シングルクォートを含まない安全なXPath式を使用
                elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), \"{text}\")]")
                if elements:
                    logger.info(f"フィードの終わりを検出: '{text}'")
                    return True
            
            # 別の方法で終了チェック: 特定の要素の有無
            try:
                end_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.x1n2onr6[role='button'][tabindex='0']")
                if len(end_elements) > 0 and "end" in end_elements[0].get_attribute("aria-label").lower():
                    logger.info("フィード終了要素を検出")
                    return True
            except Exception:
                pass
                
            return False
        except Exception as e:
            logger.warning(f"フィード終了チェック中にエラー: {e}")
            return False

    def _progressive_scroll(self, total_scrolls=10):
        """
        段階的にスクロールして確実に新しいコンテンツを読み込む
        
        Args:
            total_scrolls (int): 実行するスクロールの回数
            
        Returns:
            int: 新しく読み込まれた投稿の数
        """
        initial_posts = len(self.driver.find_elements(By.CSS_SELECTOR, "article"))
        logger.info(f"Starting progressive scroll with {initial_posts} posts")
        
        for i in range(total_scrolls):
            # 現在のウィンドウの高さを取得
            window_height = self.driver.execute_script("return window.innerHeight")
            
            # ウィンドウ高さの80%分をスクロール（重複を確保するため）
            scroll_amount = int(window_height * 0.8)
            
            # スクロール実行
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            logger.info(f"Progressive scroll #{i+1}: scrolled {scroll_amount}px")
            
            # 待機
            self._human_like_delay(2.5, 4.0)
            
            # 5回に1回、ランダムな一時停止を入れる（より人間らしく）
            if i % 5 == 4:
                pause_time = random.uniform(2.0, 5.0)
                logger.info(f"Taking a pause for {pause_time:.1f} seconds...")
                time.sleep(pause_time)
                
                # 一時停止後に少し上にスクロールしてから再度下へ（読み込みを促進）
                self.driver.execute_script("window.scrollBy(0, -300);")
                time.sleep(1)
                self.driver.execute_script("window.scrollBy(0, 350);")
                time.sleep(2)
            
            # フィードの終わりをチェック
            if self._check_end_of_feed():
                logger.info("Reached end of feed, stopping progressive scroll")
                break
        
        # 最終的なスクロール結果を確認
        final_posts = len(self.driver.find_elements(By.CSS_SELECTOR, "article"))
        new_posts = final_posts - initial_posts
        logger.info(f"Progressive scroll complete: Added {new_posts} new posts ({initial_posts} -> {final_posts})")
        
        return new_posts

    def extract_posts(self, max_posts=30, exclude_image_posts=True):
        """
        タイムラインから投稿を抽出するメソッド
        
        Args:
            max_posts (int): 取得する最大投稿数
            exclude_image_posts (bool): 画像を含む投稿を除外するかどうか
            
        Returns:
            list: (ユーザー名, 投稿テキスト, いいね数)のタプルのリスト
        """
        posts = []
        attempt_count = 0
        max_attempts = 10
        
        try:
            # ページ読み込み完了を確認
            logger.info("Waiting for page to fully load...")
            
            # より長く待機してページが完全に読み込まれるようにする
            try:
                WebDriverWait(self.driver, 20).until(  # タイムアウトを延長
                    EC.presence_of_element_located((By.TAG_NAME, "article"))
                )
                logger.info("Initial article elements found")
            except Exception as e:
                logger.warning(f"Timed out waiting for articles to load: {e}")
                # タイムアウトしても継続する
            
            # ゆっくりスクロールして内容を読み込む
            self._safe_scroll(100)
            self._human_like_delay(3.0, 5.0)
            
            # JavaScriptでページの準備状態を確認
            is_ready = self.driver.execute_script("return document.readyState") == "complete"
            logger.info(f"Page ready state: {is_ready}")
            
            # 投稿コンテナの全体的な構造
            container_selectors = [
                "div.x1ypdohk.x1n2onr6.xvuun6i",  # 提供されたHTMLから特定したコンテナクラス
                "div.xrvj5dj",  # 投稿の親コンテナ
                "article",  # 標準的な記事コンテナ
                "div[role='article']",  # role属性に基づく記事コンテナ
                "div.x1qjc9v5.x1q0g3np.x78zum5"  # 追加の投稿コンテナクラス
            ]
            
            # ユーザー名を特定するための正確なセレクタ（HTMLから）
            username_selectors = [
                "span.x1lliihq.x193iq5w.x6ikm8r.x10wlt62.xlyipyv.xuxw1ft",  # 提供されたHTMLから特定したクラス
                "a[href^='/@'] span",  # ユーザーへのリンク内のspan
                "span[translate='no']",  # 通常ユーザー名は翻訳しない
                "div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh a div.x9f619.xjbqb8w.x1rg5ohu.x168nmei.x13lgxp2.x5pf9jr.xo71vjh span",  # 追加のユーザー名セレクタ
                "div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh a span"  # 単純化したユーザー名セレクタ
            ]
            
            # 投稿テキストを特定するための正確なセレクタ（HTMLから）
            post_text_selectors = [
                "div.x1a6qonq span.x1lliihq.x1plvlek.xryxfnj",  # 提供されたHTMLから特定したクラス
                "span.x1lliihq[dir='auto'][style*='line-clamp']",  # 投稿テキストに典型的なスタイル
                "span[dir='auto']:not([translate='no'])",  # dir属性を持つが翻訳属性を持たないspan
                "div.xzsf02u.x1a2a7pz div span",  # 追加の投稿テキストセレクタ
                "div.x1iorvi4.x1pi30zi.x1l90r2v.x1swvt13 span"  # コンテンツコンテナ内のspanタグ
            ]
            
            # いいね数を特定するための正確なセレクタ（HTMLから）
            likes_selectors = [
                "span.x17qophe.x10l6tqk.x13vifvy",  # 提供されたHTMLから特定したクラス
                "div.xu9jpxn span.x17qophe",  # カウンターコンテナ内のspan
                "svg[aria-label='「いいね！」'] ~ span span",  # いいねアイコンの後のspan
                "div[role='button'] span span[dir='auto']",  # ボタン内のカウント要素
                "div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh span span"  # 複雑なパスでのカウンター
            ]
            
            # オリジナルのHTMLでの投稿コンテナ特定のためのXPath
            container_xpath = "//div[contains(@class, 'x1ypdohk') and contains(@class, 'x1n2onr6') and contains(@class, 'xvuun6i')]"
            
            while len(posts) < max_posts and attempt_count < max_attempts:
                # 現在の投稿数をログに記録
                logger.info(f"Current post count: {len(posts)}/{max_posts}, Attempt: {attempt_count+1}/{max_attempts}")
                
                # 一定回数試行してもうまくいかない場合は、別のスクロール方法を試す
                if attempt_count % 4 == 0:
                    logger.info("Using progressive scroll technique...")
                    new_posts_added = self._progressive_scroll(8)  # 段階的スクロールを実行
                    if new_posts_added == 0:
                        logger.warning("Progressive scroll didn't add any new posts")
                        
                        # ここで強制的にページ最下部までスクロール
                        logger.info("Forcing scroll to bottom...")
                        self._force_scroll_to_bottom()
                        self._human_like_delay(5.0, 7.0)
                
                # 一定間隔でページを更新
                if attempt_count >= 3 and attempt_count % 3 == 0:
                    logger.info("Refreshing page to get new content...")
                    current_url = self.driver.current_url
                    self.driver.get(current_url)
                    self._human_like_delay(5.0, 8.0)
                    self._wait_for_content_load(10)
                
                posts_found_this_round = False
                
                # 投稿コンテナを探す
                for container_selector in container_selectors:
                    try:
                        post_containers = self.driver.find_elements(By.CSS_SELECTOR, container_selector)
                        
                        if post_containers:
                            logger.info(f"Found {len(post_containers)} post containers with selector: {container_selector}")
                            
                            for container in post_containers:
                                try:
                                    # 投稿の一意のIDを生成（位置情報と内部テキストのハッシュ）
                                    try:
                                        container_id = hash(container.text[:50] + str(container.location))
                                    except Exception as e:
                                        logger.warning(f"投稿IDの生成に失敗: {e}")
                                        container_id = hash(str(container.location))
                                    
                                    # 既に処理済みの投稿はスキップ
                                    post_ids = set()  # 一時的なIDセット
                                    if container_id in post_ids:
                                        continue
                                    
                                    post_ids.add(container_id)
                                    
                                    # 画像付き投稿の検出 (新規追加)
                                    has_image = False
                                    try:
                                        # 方法1: mediaリンクを検索
                                        media_links = container.find_elements(By.CSS_SELECTOR, "a[href*='/media']")
                                        
                                        # 方法2: 画像要素を検索 (プロフィール写真を除外)
                                        images = container.find_elements(By.CSS_SELECTOR, "img:not([alt*='Profile photo'])")
                                        
                                        # 方法3: picture要素を検索
                                        pictures = container.find_elements(By.TAG_NAME, "picture")
                                        
                                        # いずれかの方法で画像を検出した場合
                                        if media_links or images or pictures:
                                            has_image = True
                                            logger.info(f"画像付き投稿を検出: ユーザー「{username}」")
                                    except Exception as e:
                                        logger.warning(f"画像検出中にエラー: {e}")
                                    
                                    # exclude_image_posts=Trueで、かつ画像付き投稿の場合はスキップ
                                    if exclude_image_posts and has_image:
                                        logger.info(f"画像付き投稿をスキップ: ユーザー「{username}」")
                                        continue
                                    
                                    # 1. ユーザー名を抽出
                                    username = None
                                    for username_selector in username_selectors:
                                        try:
                                            username_elements = container.find_elements(By.CSS_SELECTOR, username_selector)
                                            if username_elements:
                                                for element in username_elements:
                                                    potential_username = element.text.strip()
                                                    # ユーザー名のフィルタリング
                                                    if potential_username and 2 < len(potential_username) < 30:
                                                        username = potential_username
                                                        logger.info(f"Found username: {username}")
                                                        break
                                                if username:
                                                    break
                                        except:
                                            continue
                                    
                                    # 2. 投稿テキストを抽出
                                    post_text = None
                                    for text_selector in post_text_selectors:
                                        try:
                                            text_elements = container.find_elements(By.CSS_SELECTOR, text_selector)
                                            if text_elements:
                                                # 最も長いテキスト要素を選択
                                                best_text = ""
                                                for element in text_elements:
                                                    content = element.text.strip()
                                                    # 投稿テキストのフィルタリング
                                                    if content and len(content) > 5 and not self._is_ui_element_text(content):
                                                        if len(content) > len(best_text):
                                                            best_text = content
                                                
                                                if best_text:
                                                    post_text = best_text
                                                    logger.info(f"Found post text: {post_text[:50]}...")
                                                    break
                                        except:
                                            continue
                                    
                                    # 3. いいね数を抽出
                                    likes = 0
                                    for likes_selector in likes_selectors:
                                        try:
                                            likes_elements = container.find_elements(By.CSS_SELECTOR, likes_selector)
                                            if likes_elements:
                                                for element in likes_elements:
                                                    likes_text = element.text.strip()
                                                    # いいね数の正規表現パターン
                                                    like_pattern = r'^\d+$|^\d+[kK]$|^\d+\.\d+[kK]$|^\d+,\d+$'
                                                    if likes_text and re.match(like_pattern, likes_text):
                                                        try:
                                                            # K（千）単位の処理
                                                            if 'k' in likes_text.lower():
                                                                likes_text = likes_text.lower().replace('k', '')
                                                                likes = int(float(likes_text) * 1000)
                                                            else:
                                                                likes = int(likes_text.replace(',', ''))
                                                            logger.info(f"Found likes: {likes}")
                                                            break
                                                        except ValueError:
                                                            continue
                                                if likes > 0:
                                                    break
                                        except:
                                            continue
                                    
                                    # すべてのデータが取得できた場合のみ追加
                                    # ユーザー名と何らかのテキストがあれば追加（いいね数はオプショナル）
                                    if username and post_text:
                                        # ユーザー名と投稿テキストが同じ場合は除外
                                        if username != post_text:
                                            # 重複チェック - 厳密な重複チェック
                                            is_duplicate = False
                                            for existing_username, existing_text, _ in posts:
                                                # ユーザー名と投稿テキストの最初の部分が一致する場合は重複と見なす
                                                if existing_username == username and (
                                                    existing_text[:50] == post_text[:50] or 
                                                    existing_text == post_text
                                                ):
                                                    is_duplicate = True
                                                    break
                                            
                                            if not is_duplicate:
                                                posts.append((username, post_text, likes))
                                                posts_found_this_round = True
                                                logger.info(f"Added post #{len(posts)}: {username} - {post_text[:50]}... (Likes: {likes})")
                                
                                except Exception as e:
                                    logger.warning(f"Error extracting data from container: {e}")
                            
                            if posts_found_this_round:
                                break  # 成功したのでコンテナセレクタのループを抜ける
                        
                    except Exception as e:
                        logger.warning(f"Error with container selector {container_selector}: {e}")
                
                # XPathでも試行（最後の手段）
                if not posts_found_this_round:
                    try:
                        xpath_containers = self.driver.find_elements(By.XPATH, container_xpath)
                        logger.info(f"Found {len(xpath_containers)} containers using XPath")
                        
                        # ... XPath 処理のコード ...
                        
                    except Exception as e:
                        logger.warning(f"Error with XPath extraction: {e}")
            
            # 抽出ループ内でページの再読み込みを追加
            # 適切な場所に以下のコードを追加
            if attempt_count >= 3 and attempt_count % 5 == 0:
                logger.info("Refresh page to get new content...")
                current_url = self.driver.current_url
                self.driver.get(current_url)
                self._human_like_delay(5.0, 8.0)
                self._wait_for_content_load(10)
                processed_post_ids.clear()  # 処理済み投稿IDをリセット
                    
            # 投稿抽出のメインループ内でスクロール量を強化
            self._safe_scroll(random.randint(1200, 2000))  # スクロール量を大幅に増加
            
            return posts
        
        except Exception as e:
            logger.error(f"Error during extraction: {e}")
            logger.error(traceback.format_exc())
            return []

    def save_to_csv(self, posts, filename=None, min_likes=0):
        """
        投稿データをCSVに保存（投稿者、投稿内容、いいね数を別カラムに）
        
        Args:
            posts (list): (投稿者, 投稿テキスト, いいね数)のタプルのリスト
            filename (str): 保存するファイル名 (Noneの場合は日時を含む名前が自動生成される)
            min_likes (int): 保存する最小いいね数（これ以下のいいね数の投稿はフィルタリング）
        
        Returns:
            tuple: (元データのファイル名, フィルター後のファイル名)
        """
        try:
            # デフォルトのファイル名を設定 (日付と時間を含む)
            if filename is None:
                now = datetime.datetime.now()
                filename = f"threads_posts_{now.strftime('%m%d_%H%M')}.csv"
            
            # データフレームを作成する前に重複や不要データをクリーニング
            cleaned_posts = []
            seen_posts = set()  # 重複チェック用
            
            for username, post_text, likes in posts:
                # 重複チェック
                post_identifier = f"{username}:{post_text[:20]}"
                if post_identifier in seen_posts:
                    continue
                
                # 投稿者名クリーニング
                # 数字だけのユーザー名は通常本物のユーザーではない
                if not username or username.isdigit():  # 'おすすめ'は有効な投稿ソースにする
                    continue
                    
                # 投稿テキストクリーニング
                # 明らかに広告やスパム投稿を除外
                spam_patterns = [
                    "100円note", "月5万", "裏技", "副業", "スキル０", "在宅", "稼げる",
                    "Line登録", "権利収入", "不労所得"
                ]
                
                # 少なくとも一つのスパムパターンを含む場合はスキップ
                if any(pattern in post_text for pattern in spam_patterns):
                    continue
                    
                # 短すぎる投稿は除外
                if len(post_text) < 5:
                    continue
                    
                # メタデータや時間表示のみの投稿を除外
                if post_text in [username, f"{username}_", f"@{username}"]:
                    continue
                    
                # UI要素っぽいテキストを除外
                if self._is_ui_element_text(post_text):
                    continue
                
                # ユーザー名と同じ投稿テキストを除外
                if username == post_text:
                    continue
                    
                # クリーニングしたデータを追加
                cleaned_posts.append((username, post_text, likes))
                seen_posts.add(post_identifier)
            
            # データフレーム作成と保存
            if cleaned_posts:
                df = pd.DataFrame(cleaned_posts, columns=["username", "post_text", "likes"])
                
                # 元のCSVファイルを保存
                original_filename = filename
                df.to_csv(original_filename, index=False, encoding='utf-8-sig')
                logger.info(f"Saved {len(cleaned_posts)} cleaned posts to {original_filename}")
                
                # いいね数でフィルタリング
                if min_likes > 0:
                    filtered_df = df[df['likes'] > min_likes]
                    filtered_count = len(filtered_df)
                    
                    # フィルター後のファイル名を生成
                    filtered_filename = original_filename.replace('.csv', f'_likes{min_likes}plus.csv')
                    
                    # フィルター後のデータを保存
                    filtered_df.to_csv(filtered_filename, index=False, encoding='utf-8-sig')
                    logger.info(f"Filtered to {filtered_count} posts with more than {min_likes} likes in {filtered_filename}")
                    
                    # 削除された投稿数を表示
                    removed_count = len(df) - filtered_count
                    logger.info(f"Removed {removed_count} posts with {min_likes} or fewer likes")
                    
                    return original_filename, filtered_filename
                
                return original_filename, None
            else:
                logger.warning("No valid posts to save after cleaning")
                return None, None
        except Exception as e:
            logger.error(f"Error saving posts to CSV: {e}")
            return None, None

    def close(self):
        """
        WebDriverを安全に閉じるメソッド
        """
        try:
            if hasattr(self, 'driver') and self.driver:
                self.driver.quit()
                logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    def _wait_for_page_load(self, timeout=10):
        """
        ページの読み込みが完了するのを待つ
        
        Args:
            timeout (int): 最大待機時間（秒）
            
        Returns:
            bool: ページが正常に読み込まれたかどうか
        """
        try:
            # DOMの読み込み完了を待機
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            # ページがロードされたことをログに記録
            current_url = self.driver.current_url
            logger.info(f"Page loaded: {current_url}")
            
            return True
        except Exception as e:
            logger.warning(f"Page load wait timed out or failed: {e}")
            return False

    def extract_posts_from_search(self, keyword, max_posts=100, exclude_image_posts=True, min_likes=0, target=None, debug_mode=False):
        """
        検索結果ページから投稿を抽出する
        
        Args:
            keyword (str): 検索キーワード
            max_posts (int): 取得する最大投稿数
            exclude_image_posts (bool): 画像付き投稿を除外するかどうか
            min_likes (int): 最小いいね数（これ未満の投稿は除外）
            target (str): ターゲット名（記録用）
            debug_mode (bool): デバッグモード（Trueの場合、画像判定を無視してすべての投稿を取得）
        
        Returns:
            list: 抽出された投稿のリスト
        """
        posts = []
        local_post_ids = set()  # 重複排除用のローカルセット
        
        try:
            # 検索ページへの移動
            if not self.navigate_to_search_page(keyword):
                logger.error(f"検索ページへの移動に失敗: {keyword}")
                return posts
                
            # ページロード待機
            self._wait_for_page_load(10)
            
            # 最下部スクロールを10回実行（新しい機能を使用）
            self._scroll_to_bottom(count=10)
            
            # 投稿コンテナの取得
            containers = self._get_post_elements()
            logger.info(f"{len(containers)}個の投稿コンテナを検出")
            
            # 各投稿を処理
            for i, container in enumerate(containers):
                try:
                    # デバッグモードの場合、HTMLを保存
                    if debug_mode and i < 5:  # 最初の5件のみ保存
                        self._save_post_html_for_debug(container, i, keyword)
                    
                    # ユーザー名を取得
                    try:
                        # 複数のセレクタを試行
                        username_selectors = [
                            "span.xu06os2[dir='auto']",
                            "a[href^='/@'] span",
                            "div.xqcrz7y a[href^='/@']"
                        ]
                        
                        username = "unknown"
                        for selector in username_selectors:
                            try:
                                user_element = container.find_element(By.CSS_SELECTOR, selector)
                                username = user_element.text.strip()
                                if username and not username.startswith("@"):
                                    username = username.replace("@", "")
                                if username:
                                    break
                            except:
                                continue
                        
                        # バックアップ方法: hrefから抽出
                        if username == "unknown":
                            try:
                                href_element = container.find_element(By.CSS_SELECTOR, "a[href^='/@']")
                                href = href_element.get_attribute("href")
                                username = href.split("/@")[1].split("/")[0]
                            except:
                                pass
                    except Exception as ue:
                        logger.warning(f"ユーザー名取得エラー: {ue}")
                        username = "unknown"
                    
                    # 投稿テキストを取得
                    post_text = self._extract_post_text(container)
                    
                    # 一意のIDを生成（コンテナの位置とテキストからハッシュ）
                    try:
                        # このライン重要: container_id を定義
                        container_id = f"{username}:{post_text[:30]}"
                    except Exception as ide:
                        logger.warning(f"ID生成エラー: {ide}")
                        container_id = f"post_{i}"
                    
                    # 重複チェック - これがエラーになっていた行
                    if container_id not in local_post_ids:
                        # 画像の有無を判定
                        has_images = self._has_images(container)
                        
                        # 画像付き投稿を除外するかどうかのチェック
                        if not exclude_image_posts or not has_images or debug_mode:
                            # いいね数を取得
                            likes = self._extract_likes(container)
                            
                            # いいね数の最小値チェック
                            if likes >= min_likes:
                                # 投稿を追加 - ここでターゲット情報も追加
                                posts.append((username, post_text, likes, target))
                                # IDを保存して重複を防止
                                local_post_ids.add(container_id)
                                
                                logger.info(f"投稿を追加: {username}, いいね={likes}, 内容={post_text[:50]}...")
                                
                                # 最大投稿数に達したら終了
                                if len(posts) >= max_posts:
                                    logger.info(f"最大投稿数 {max_posts} に達したため終了")
                                    break
                            else:
                                logger.info(f"いいね数が少ない投稿をスキップ: {likes} < {min_likes}")
                        else:
                            logger.info(f"画像付き投稿をスキップ: {container_id}")
                    else:
                        logger.info(f"重複投稿をスキップ: {container_id}")
                        
                except Exception as post_e:
                    logger.warning(f"投稿 {i+1} の処理中にエラー: {post_e}")
                    continue
                    
            logger.info(f"検索「{keyword}」から {len(posts)} 件の投稿を抽出")
            return posts
            
        except Exception as e:
            logger.error(f"検索抽出中にエラー: {e}")
            logger.error(traceback.format_exc())
            return posts

    def save_to_csv(self, posts, filename=None, min_likes=0):
        """
        投稿データをCSVに保存（投稿者、投稿内容、いいね数、ターゲットを別カラムに）
        
        Args:
            posts (list): (投稿者, 投稿テキスト, いいね数, ターゲット)のタプルのリスト
            filename (str): 保存するファイル名 (Noneの場合は日時を含む名前が自動生成される)
            min_likes (int): 保存する最小いいね数（これ以下のいいね数の投稿はフィルタリング）
        
        Returns:
            str: 保存されたファイルのパス
        """
        try:
            # デフォルトのファイル名を設定 (日付と時間を含む)
            if filename is None:
                now = datetime.datetime.now()
                filename = f"threads_posts_{now.strftime('%m%d_%H%M')}.csv"
            
            # データフレームを作成する前に重複や不要データをクリーニング
            cleaned_posts = []
            seen_posts = set()  # 重複チェック用
            
            for username, post_text, likes, target in posts:
                # 重複チェック
                post_identifier = f"{username}:{post_text[:20]}"
                if post_identifier in seen_posts:
                    continue
                
                # 投稿者名クリーニング
                # 数字だけのユーザー名は通常本物のユーザーではない
                if not username or username.isdigit():  # 'おすすめ'は有効な投稿ソースにする
                    continue
                    
                # 投稿テキストクリーニング
                # 明らかに広告やスパム投稿を除外
                spam_patterns = [
                    "100円note", "月5万", "裏技", "副業", "スキル０", "在宅", "稼げる",
                    "Line登録", "権利収入", "不労所得"
                ]
                
                # 少なくとも一つのスパムパターンを含む場合はスキップ
                if any(pattern in post_text for pattern in spam_patterns):
                    continue
                    
                # 短すぎる投稿は除外
                if len(post_text) < 5:
                    continue
                    
                # メタデータや時間表示のみの投稿を除外
                if post_text in [username, f"{username}_", f"@{username}"]:
                    continue
                    
                # UI要素っぽいテキストを除外
                if self._is_ui_element_text(post_text):
                    continue
                
                # ユーザー名と同じ投稿テキストを除外
                if username == post_text:
                    continue
                    
                # クリーニングしたデータを追加
                cleaned_posts.append((username, post_text, likes, target))
                seen_posts.add(post_identifier)
            
            # データフレーム作成と保存
            if cleaned_posts:
                df = pd.DataFrame(cleaned_posts, columns=["username", "post_text", "likes", "target"])
                
                # 元のCSVファイルを保存
                df.to_csv(filename, index=False, encoding='utf-8-sig')
                logger.info(f"Saved {len(cleaned_posts)} cleaned posts to {filename}")
                
                # いいね数でフィルタリング
                if min_likes > 0:
                    filtered_df = df[df['likes'] >= min_likes]
                    filtered_count = len(filtered_df)
                    
                    # いいね数による選別結果をログに記録
                    logger.info(f"Filtered to {filtered_count} posts with {min_likes} or more likes")
                    
                    # フィルター後のデータを同じファイル名で上書き保存
                    if filtered_count > 0:
                        filtered_df.to_csv(filename, index=False, encoding='utf-8-sig')
                        logger.info(f"Saved {filtered_count} filtered posts to {filename}")
                        
                        # 削除された投稿数を表示
                        removed_count = len(df) - filtered_count
                        logger.info(f"Removed {removed_count} posts with fewer than {min_likes} likes")
                    else:
                        logger.warning(f"No posts with {min_likes} or more likes found. Original file preserved.")
                
                return filename
            else:
                logger.warning("No valid posts to save after cleaning")
                return None
        except Exception as e:
            logger.error(f"Error saving posts to CSV: {e}")
            return None

    def navigate_to_search_page(self, keyword):
        """
        検索ページに移動する
        
        Args:
            keyword (str): 検索するキーワード
            
        Returns:
            bool: 検索ページへの移動に成功したかどうか
        """
        try:
            # URLエンコードされたキーワードを作成
            encoded_keyword = urllib.parse.quote(keyword)
            search_url = f"https://www.threads.net/search?q={encoded_keyword}&serp_type=default"
            
            logger.info(f"Navigating to search page for keyword: {keyword}")
            self.driver.get(search_url)
            
            # ページの読み込みを待つ
            self._wait_for_page_load(20)
            
            # 人間らしい遅延
            self._human_like_delay(3.0, 5.0)
            
            # 検索結果ページかどうか確認
            if "search" in self.driver.current_url and keyword.lower() in self.driver.page_source.lower():
                logger.info(f"Successfully navigated to search page for: {keyword}")
                # コンテンツが完全に読み込まれるのを待つ
                self._wait_for_content_load(10)
                return True
            else:
                logger.warning(f"Failed to navigate to search page for: {keyword}")
                # 現在のURLをログに記録
                logger.warning(f"Current URL: {self.driver.current_url}")
                return False
        except Exception as e:
            logger.error(f"Error navigating to search page for keyword '{keyword}': {e}")
            logger.error(traceback.format_exc())
            return False

    def _has_images(self, element):
        """
        投稿要素に画像や動画が含まれているかどうかを正確に判定する
        
        Args:
            element: 投稿要素
            
        Returns:
            bool: 画像や動画が含まれる場合はTrue、それ以外はFalse
        """
        try:
            # ボタン内のSVGやアイコン画像を除外した実際の投稿画像を検索
            # プロフィール写真とボタンアイコンを除外 (日本語と英語の両方に対応)
            images = element.find_elements(By.CSS_SELECTOR, 
                "img:not([alt*='Profile photo']):not([alt*='プロフィール写真']):not([alt='「いいね！」']):not([alt='いいね！']):not([alt='返信']):not([alt='Reply']):not([alt='再投稿']):not([alt='Repost']):not([alt='シェアする']):not([alt='Share'])")
            
            # インタラクティブなメディア要素（動画など）を検索
            media_containers = element.find_elements(By.CSS_SELECTOR, 
                "div[role='button'][tabindex='0'][aria-label*='投稿'], div[role='button'][tabindex='0'][aria-label*='post']")
            
            # 画像スタイルを持つ特定の親コンテナを検索（画像の別のパターン）
            image_containers = element.find_elements(By.CSS_SELECTOR, 
                "div.xod5an3:not(:empty), div.x1gg8mnh:not(:empty)")
            
            # リアクションボタンだけを持つ要素を除外するための追加チェック
            reaction_buttons = element.find_elements(By.CSS_SELECTOR,
                "div.x4vbgl9 div.x1i10hfl[role='button']")
            
            logger.info(f"画像/メディア要素の検出: 画像={len(images)}, メディア={len(media_containers)}, 画像コンテナ={len(image_containers)}")
            
            # 本文テキスト要素を取得（これがあり、他のメディア要素がなければテキストのみの投稿）
            text_elements = element.find_elements(By.CSS_SELECTOR, "span.x1lliihq[dir='auto']")
            
            # デバッグ情報の追加：検出された画像の詳細をログに出力
            if len(images) > 0:
                for i, img in enumerate(images):
                    try:
                        alt = img.get_attribute('alt') or "なし"
                        src = img.get_attribute('src') or "なし"
                        width = img.get_attribute('width') or "不明"
                        height = img.get_attribute('height') or "不明"
                        
                        # プロフィール写真やアイコンの可能性がある小さな画像を除外
                        is_small_icon = (alt and ('プロフィール' in alt or 'Profile' in alt or 'いいね' in alt or 'Like' in alt)) or \
                                       ((width != "不明" and height != "不明") and (int(width) < 50 or int(height) < 50))
                        
                        logger.info(f"画像 {i+1} の属性: alt='{alt}', サイズ={width}x{height}, アイコン判定={is_small_icon}")
                        
                        # プロフィール写真やアイコンと判断される画像はカウントから除外
                        if is_small_icon:
                            images.remove(img)
                    except Exception as img_e:
                        logger.warning(f"画像属性取得エラー: {img_e}")
            
            # リアクションボタンのみの場合は画像付き投稿と判定しない
            if len(reaction_buttons) > 0 and len(images) == 0 and len(media_containers) == 0 and len(image_containers) == 0:
                logger.info("リアクションボタンのみ検出 - 画像なしと判定")
                return False
            
            # 実際の投稿画像があるかどうかの判定を厳格化
            if len(images) > 0 or len(media_containers) > 0 or len(image_containers) > 0:
                logger.info("画像付き投稿を検出")
                return True
            else:
                logger.info("テキストのみの投稿と判定")
                return False
                
        except Exception as e:
            logger.warning(f"画像判定中にエラー: {e}")
            traceback.print_exc()
            return False

    def _extract_post_text(self, container):
        """
        投稿コンテナからテキストを抽出する
        """
        try:
            # 投稿の本文テキストを直接取得するセレクタを使用
            # 投稿本文は複数のspanに分かれている場合がある
            text_spans = container.find_elements(By.CSS_SELECTOR, "div.x1a6qonq x6ikm8r x10wlt62 xj0a0fe x126k92a x6prxxf x7r5mf7 span")
            if not text_spans:
                # より一般的なセレクタを試す
                text_spans = container.find_elements(By.CSS_SELECTOR, "div.x1a6qonq span")
            
            # すべてのテキストスパンを連結
            post_text = " ".join([span.text.strip() for span in text_spans if span.text.strip()])
            
            # ハッシュタグもテキストとして含める
            hashtags = container.find_elements(By.CSS_SELECTOR, "a[href*='search?q=']")
            hashtag_texts = [tag.text.strip() for tag in hashtags if tag.text.strip()]
            
            # ハッシュタグを投稿テキストに追加
            if hashtag_texts:
                hashtag_str = " ".join(hashtag_texts)
                if post_text:
                    post_text = f"{post_text} {hashtag_str}"
                else:
                    post_text = hashtag_str
                    
            # テキストが見つからない場合は別の方法を試す
            if not post_text:
                # 直接コンテナ内のテキストを取得
                post_text = container.find_element(By.CSS_SELECTOR, "div.x1xdureb").text.strip()
                
                # ユーザー名と日付部分を取り除く
                username_elements = container.find_elements(By.CSS_SELECTOR, "a[href^='/@']")
                for element in username_elements:
                    if element.text.strip() in post_text:
                        post_text = post_text.replace(element.text.strip(), "").strip()
                
                # 日付/時間要素を削除
                time_elements = container.find_elements(By.CSS_SELECTOR, "time")
                for time_el in time_elements:
                    if time_el.text.strip() in post_text:
                        post_text = post_text.replace(time_el.text.strip(), "").strip()
            
            return post_text.strip()
        except Exception as e:
            logger.warning(f"テキスト抽出エラー: {e}")
            return ""

    def _extract_likes(self, element):
        """
        投稿要素からいいね数を抽出する
        
        Args:
            element: 投稿要素
            
        Returns:
            int: いいね数（取得できない場合は0）
        """
        try:
            # いいね数の要素を検索
            like_elements = element.find_elements(By.CSS_SELECTOR, "span.x17qophe")
            
            if like_elements:
                like_text = like_elements[0].text.strip()
                
                # 「K」や「万」などの省略形を処理
                if 'K' in like_text or 'k' in like_text:
                    return int(float(like_text.replace('K', '').replace('k', '')) * 1000)
                elif '万' in like_text:
                    return int(float(like_text.replace('万', '')) * 10000)
                else:
                    # 数字だけを抽出
                    return int(''.join(filter(str.isdigit, like_text)) or 0)
            
            return 0
        except Exception as e:
            logger.warning(f"いいね数抽出中にエラー: {e}")
            return 0

    def _get_post_elements(self):
        """
        ページから投稿要素を取得する改良版メソッド
        
        Returns:
            list: 投稿要素のリスト
        """
        try:
            # 複数のセレクタを試す
            selector_attempts = [
                "article",  # 記事コンテナ
                "div.x1ypdohk.x1n2onr6.xvuun6i",  # 投稿コンテナ
                "div.xrvj5dj", # 別の投稿コンテナ
                "div[role='article']"  # 記事ロールを持つdiv
            ]
            
            post_elements = []
            
            for selector in selector_attempts:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.info(f"Found {len(elements)} post containers with selector: {selector}")
                    if not post_elements:  # まだ要素が見つかっていない場合のみ更新
                        post_elements = elements
                    
            # 投稿コンテナがまだ見つからない場合はXPathも試す
            if not post_elements:
                xpath_expression = "//div[contains(@class, 'x1ypdohk') and contains(@class, 'x1n2onr6')]"
                post_elements = self.driver.find_elements(By.XPATH, xpath_expression)
                logger.info(f"Found {len(post_elements)} containers using XPath")
                
            # 見つかった要素を返す
            return post_elements
            
        except Exception as e:
            logger.warning(f"投稿要素の取得中にエラー: {e}")
            return []

    def _save_post_html_for_debug(self, element, index, prefix="post"):
        """
        デバッグ用に投稿のHTMLをファイルに保存
        
        Args:
            element: 投稿要素
            index: 投稿のインデックス
            prefix: ファイル名のプレフィックス
        """
        try:
            debug_dir = "debug_html"
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            html_content = element.get_attribute('outerHTML')
            filename = f"{debug_dir}/{prefix}_{index}_{timestamp}.html"
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{html_content}</body></html>")
            
            logger.info(f"投稿{index}のHTMLを保存: {filename}")
        except Exception as e:
            logger.warning(f"HTML保存中にエラー: {e}")

    def _scroll_to_bottom(self, count=10):
        """
        ページの最下部まで指定回数スクロールする
        
        Args:
            count (int): 最下部までスクロールする回数
        
        Returns:
            int: 検出した投稿数
        """
        logger.info(f"ページ最下部への到達を {count} 回実行します")
        
        last_height = 0
        post_count = 0
        
        for i in range(count):
            # 現在の投稿数を取得
            current_posts = self._get_post_elements()
            post_count = len(current_posts)
            
            # 最下部までスクロール
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            logger.info(f"スクロール {i+1}/{count}: 最下部に到達しました (現在の投稿: {post_count}件)")
            
            # スクロール後に短い待機
            self._human_like_delay(2.0, 3.0)
            
            # 現在の高さを取得
            current_height = self.driver.execute_script("return document.body.scrollHeight")
            
            # ページの高さが変わらなければ、新しいコンテンツがロードされなかった可能性がある
            if current_height == last_height:
                # コンテンツの読み込みをもう少し待つ
                logger.info("ページの高さが変わらないため、追加で待機...")
                self._human_like_delay(3.0, 5.0)
                
                # 「もっと見る」ボタンがあれば押す
                try:
                    more_buttons = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'もっと見る') or contains(text(), 'See more')]")
                    if more_buttons:
                        more_buttons[0].click()
                        logger.info("「もっと見る」ボタンをクリックしました")
                        self._human_like_delay(2.0, 3.0)
                except Exception as e:
                    logger.debug(f"「もっと見る」ボタンの操作に失敗: {e}")
            
            # 高さを更新
            last_height = current_height
        
        # 最後に検出された投稿数を返す
        final_posts = self._get_post_elements()
        logger.info(f"最下部スクロール完了: 合計 {len(final_posts)}件 の投稿を検出")
        return len(final_posts)

    # 1. _wait_for_element メソッドの追加 - 待機処理を統合
    def _wait_for_element(self, by, selector, timeout=10, condition="presence"):
        """
        要素の待機処理を統合したヘルパーメソッド
        
        Args:
            by: 検索方法 (By.ID, By.CSS_SELECTOR など)
            selector: 要素のセレクタ
            timeout: 最大待機時間(秒)
            condition: 待機条件 ("presence", "clickable", "visible")
            
        Returns:
            見つかった要素またはNone
        """
        try:
            if condition == "clickable":
                element = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((by, selector))
                )
            elif condition == "visible":
                element = WebDriverWait(self.driver, timeout).until(
                    EC.visibility_of_element_located((by, selector))
                )
            else:  # presence
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, selector))
                )
            return element
        except Exception as e:
            logger.debug(f"要素待機タイムアウト - {selector}: {e}")
            return None

    # 2. _is_spam_post メソッドの追加 - スパム判定ロジックを統合
    def _is_spam_post(self, username, post_text):
        """
        スパム投稿かどうかを判定するメソッド
        
        Args:
            username: 投稿者名
            post_text: 投稿テキスト
            
        Returns:
            bool: スパム投稿であればTrue
        """
        # ユーザー名チェック - 数字だけのユーザー名は通常本物のユーザーではない
        if not username or username.isdigit():
            return True
            
        # 投稿テキストチェック - 明らかな広告やスパム
        spam_patterns = [
            "100円note", "月5万", "裏技", "副業", "スキル０", "在宅", "稼げる",
            "Line登録", "権利収入", "不労所得"
        ]
        
        # スパムパターンを含む場合はスパム判定
        if any(pattern in post_text for pattern in spam_patterns):
            return True
            
        # 短すぎる投稿は除外
        if len(post_text) < 5:
            return True
            
        # メタデータや時間表示のみの投稿を除外
        if post_text in [username, f"{username}_", f"@{username}"]:
            return True
            
        # ユーザー名と同じ投稿テキストを除外
        if username == post_text:
            return True
        
        # UI要素っぽいテキストを除外（既存の_is_ui_element_textメソッドを使用）
        if self._is_ui_element_text(post_text):
            return True
            
        return False

    # 3. extract_post_data メソッドの改善 - データ抽出ロジックの整理
    def extract_post_data(self, article, target=None):
        """
        投稿記事から必要なデータを抽出する
        
        Args:
            article: 投稿記事要素
            target: ターゲット名（オプション）
            
        Returns:
            tuple: (username, post_text, likes, has_image) または None
        """
        try:
            # ユーザー名の抽出を試みる（複数のセレクタパターンを試す）
            username = None
            username_selectors = [
                "span.xu06os2[dir='auto']",
                "a[href^='/@'] span",
                "div.xqcrz7y a[href^='/@']"
            ]
            
            # セレクタを順に試す
            for selector in username_selectors:
                try:
                    username_element = article.find_element(By.CSS_SELECTOR, selector)
                    username = username_element.text.strip()
                    if username:
                        if username.startswith("@"):
                            username = username[1:]
                        break
                except:
                    continue
                    
            # バックアップ: hrefから抽出
            if not username:
                try:
                    href_element = article.find_element(By.CSS_SELECTOR, "a[href^='/@']")
                    href = href_element.get_attribute("href")
                    username = href.split("/@")[1].split("/")[0]
                except:
                    username = "unknown"
                    
            # 投稿テキストの抽出を試みる（複数のセレクタパターンを試す）
            post_text = None
            text_selectors = [
                "div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x1vvkbs",
                "div[dir='auto']",
                "span[dir='auto']"
            ]
            
            # より確実なセレクタでテキスト要素を探す
            for selector in text_selectors:
                try:
                    text_elements = article.find_elements(By.CSS_SELECTOR, selector)
                    # 最も長いテキストを選択（通常は投稿本文が最長）
                    if text_elements:
                        longest_text = max([e.text.strip() for e in text_elements if e.text.strip()], 
                                         key=len, default="")
                        if longest_text and len(longest_text) > 3:  # 最低限の長さをチェック
                            post_text = longest_text
                            break
                except:
                    continue
                    
            if not post_text:
                # 最後の手段としてページのテキストから抽出を試みる
                try:
                    # 記事全体のテキストを取得
                    full_text = article.text
                    # 行に分割して短すぎない行を選択
                    lines = [line.strip() for line in full_text.split('\n') if len(line.strip()) > 5]
                    if lines:
                        # ユーザー名を含まない最長の行を選択
                        filtered_lines = [line for line in lines if username not in line]
                        post_text = max(filtered_lines, key=len) if filtered_lines else lines[0]
                except:
                    post_text = ""
                    
            # いいね数の抽出
            likes = 0
            try:
                likes_elements = article.find_elements(By.CSS_SELECTOR, "span.x1lliihq")
                for element in likes_elements:
                    text = element.text.strip()
                    # いいね数の形式をチェック（例: "123件" や "1.2K件"）
                    if text and ('件' in text or 'K' in text or 'M' in text):
                        # 数値部分を抽出
                        num_str = ''.join(c for c in text if c.isdigit() or c == '.' or c == 'K' or c == 'M')
                        # 単位に応じて変換
                        if 'K' in num_str:
                            likes = int(float(num_str.replace('K', '')) * 1000)
                        elif 'M' in num_str:
                            likes = int(float(num_str.replace('M', '')) * 1000000)
                        else:
                            try:
                                likes = int(float(num_str))
                            except:
                                likes = 0
                        break
            except Exception as e:
                logger.debug(f"いいね数の抽出に失敗: {e}")
                
            # 画像付き投稿かどうかを確認
            has_image = False
            try:
                images = article.find_elements(By.TAG_NAME, "img")
                # プロフィール画像以外の画像が存在するか
                has_image = len([img for img in images if not (
                    'profile' in (img.get_attribute('alt') or '').lower() or
                    'avatar' in (img.get_attribute('class') or '').lower()
                )]) > 0
            except:
                pass
                
            # スパムチェック
            if self._is_spam_post(username, post_text):
                return None
                
            return (username, post_text, likes, has_image)
            
        except Exception as e:
            logger.debug(f"投稿データ抽出エラー: {e}")
            return None

    # 4. save_to_csv メソッドの効率化
    def save_to_csv(self, posts, filename=None, min_likes=0):
        """
        抽出した投稿をCSVファイルに保存する
        
        Args:
            posts: 投稿データのリスト (username, post_text, likes, target)
            filename: 保存先ファイル名
            min_likes: 保存する最小いいね数
            
        Returns:
            str: 保存したファイルパス、または失敗した場合はNone
        """
        if not posts:
            logger.warning("保存する投稿がありません")
            return None
            
        try:
            # デフォルトのファイル名を設定
            if not filename:
                now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"data/threads_posts_{now}.csv"
                
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            # 重複チェック用セットと保存用リストを初期化
            seen_posts = set()
            cleaned_posts = []
                
            for username, post_text, likes, target in posts:
                # いいね数フィルタリング
                if likes < min_likes:
                    continue
                    
                # 重複チェック
                post_identifier = f"{username}:{post_text[:20]}"
                if post_identifier in seen_posts:
                    continue
                    
                # ここでは_is_spam_postはすでに適用済みと仮定
                    
                # クリーニングしたデータを追加
                cleaned_posts.append((username, post_text, likes, target))
                seen_posts.add(post_identifier)
                    
            # データフレームに変換
            df = pd.DataFrame(cleaned_posts, columns=["username", "post_text", "likes", "target"])
            
            # CSVに保存
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            logger.info(f"{len(cleaned_posts)}件の投稿を {filename} に保存しました")
            
            return filename
        
        except Exception as e:
            logger.error(f"CSVファイル保存エラー: {e}")
            return None

    def search_keyword(self, keyword, max_posts=10, min_likes=500):
        """
        キーワードで検索して投稿を取得するためのラッパーメソッド
        
        Args:
            keyword (str): 検索キーワード
            max_posts (int): 取得する最大投稿数
            min_likes (int): 最小いいね数
            
        Returns:
            list: (username, post_text, likes) のタプルのリスト
        """
        logger.info(f"Searching for keyword: {keyword} (max: {max_posts}, min likes: {min_likes})")
        
        posts = self.extract_posts_from_search(
            keyword=keyword,
            max_posts=max_posts,
            exclude_image_posts=True,
            min_likes=min_likes,
            target=""  # 空文字列を渡す（既存のAPIとの互換性のため）
        )
        
        logger.info(f"Found {len(posts)} posts for keyword: {keyword}")
        
        return posts

def get_accounts_from_env():
    """
    .env ファイルから複数のアカウント情報を取得
    
    Returns:
        list: (username, password)のタプルのリスト
    """
    accounts = []
    
    # 複数アカウントのパターンをチェック（USERNAME1, USERNAME2, ...）
    index = 1
    while True:
        username_key = f"THREADS_USERNAME{index}"
        password_key = f"THREADS_PASSWORD{index}"
        
        username = os.environ.get(username_key)
        password = os.environ.get(password_key)
        
        # 両方の値が存在する場合のみアカウントとして追加
        if username and password:
            accounts.append((username, password))
            logger.info(f"Found account #{index}: {username[:2]}*** (credentials length: {len(username)}/{len(password)})")
            index += 1
        else:
            # 連番が途切れたらループを終了
            break
    
    # 通常の変数名も確認（THREADS_USERNAME, THREADS_PASSWORD）
    username = os.environ.get("THREADS_USERNAME")
    password = os.environ.get("THREADS_PASSWORD")
    
    if username and password and (username, password) not in accounts:
        accounts.append((username, password))
        logger.info(f"Found default account: {username[:2]}*** (credentials length: {len(username)}/{len(password)})")
    
    return accounts

def load_config(config_file='config.json'):
    """
    設定ファイルからターゲットとキーワードを読み込む
    
    Args:
        config_file (str): 設定ファイルのパス
        
    Returns:
        list: ターゲット情報のリスト [{'name': 'ターゲット名', 'keywords': [キーワード1, キーワード2, ...]}]
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        targets = config.get('targets', [])
        if not targets:
            logger.warning(f"No targets found in config file: {config_file}")
        else:
            logger.info(f"Loaded {len(targets)} targets from config file")
            for target in targets:
                logger.info(f"Target: {target['name']}, Keywords: {', '.join(target['keywords'])}")
        
        return targets
    except Exception as e:
        logger.error(f"Error loading config file: {e}")
        return []

def create_data_directory():
    """
    データ保存用のディレクトリを作成する
    
    Returns:
        str: 作成されたディレクトリのパス
    """
    # データディレクトリが存在しない場合は作成
    if not os.path.exists('data'):
        os.makedirs('data')
        logger.info("Created 'data' directory")
    
    # 現在の日時を含むディレクトリ名を生成
    now = datetime.datetime.now()
    dir_name = f"data/{now.strftime('%Y%m%d_%H%M%S')}"
    
    # ディレクトリを作成
    os.makedirs(dir_name)
    logger.info(f"Created data directory: {dir_name}")
    
    return dir_name

def scrape_threads_by_keywords(max_posts_per_keyword=30, headless=False, exclude_image_posts=True, min_likes=500):
    """
    設定ファイルからキーワードを読み込み、Threadsでキーワード検索した結果をスクレイピングする
    
    Args:
        max_posts_per_keyword (int): 1キーワードあたりの最大取得投稿数
        headless (bool): ヘッドレスモードで実行するかどうか
        exclude_image_posts (bool): 画像付き投稿を除外するかどうか
        min_likes (int): フィルタリングするいいねの最小数
        
    Returns:
        str: 保存したデータディレクトリのパス、または失敗時はNone
    """
    # 設定ファイルを読み込む
    targets = load_config()
    if not targets:
        logger.error("No valid targets found in config file")
        return None
    
    # .envファイルからアカウント情報を取得
    accounts = get_accounts_from_env()
    
    if not accounts:
        logger.warning("アカウント情報が見つかりません。ログインなしでスクレイピングを試みます。")
        accounts = [("", "")]  # 空のログイン情報
    
    # データ保存用のディレクトリを作成
    data_dir = create_data_directory()
    
    # アカウントごとに処理するターゲットを分散
    account_count = max(1, len(accounts))
    targets_per_account = [[] for _ in range(account_count)]
    
    # ターゲットを各アカウントに分配
    for i, target in enumerate(targets):
        account_index = i % account_count
        targets_per_account[account_index].append(target)
    
    # 各アカウントでスクレイピングを実行
    for account_index, (username, password) in enumerate(accounts):
        account_targets = targets_per_account[account_index]
        if not account_targets:
            logger.info(f"No targets assigned to account {account_index+1}")
            continue
        
        logger.info(f"Processing {len(account_targets)} targets with account {account_index+1}")
        
        # スクレイパーを初期化
        scraper = ThreadsScraper(headless=headless)
        
        try:
            # ログイン
            logged_in = False
            if username and password:
                try:
                    scraper.driver.get("https://www.threads.net/login")
                    scraper._wait_for_page_load()
                    logged_in = scraper.login(username, password)
                    if logged_in:
                        logger.info(f"Successfully logged in with account {account_index+1}")
                    else:
                        logger.warning(f"Login failed for account {account_index+1}")
                except Exception as e:
                    logger.error(f"Error during login: {e}")
            
            # 各ターゲットとキーワードで検索
            for target in account_targets:
                target_name = target.get('name', 'unknown')
                keywords = target.get('keywords', [])
                
                if not keywords:
                    logger.warning(f"No keywords found for target: {target_name}")
                    continue
                
                logger.info(f"Processing target: {target_name} with {len(keywords)} keywords")
                
                all_posts = []
                
                # 各キーワードで検索
                for keyword in keywords:
                    logger.info(f"Searching for keyword: {keyword}")
                    
                    posts = scraper.extract_posts_from_search(
                        keyword=keyword,
                        max_posts=max_posts_per_keyword,
                        exclude_image_posts=exclude_image_posts,
                        min_likes=min_likes,
                        target=target_name
                    )
                    
                    logger.info(f"Collected {len(posts)} posts for keyword: {keyword}")
                    all_posts.extend(posts)
                    
                    # 連続検索の間に適度な待機
                    scraper._human_like_delay(4.0, 8.0)
                
                # 重複を除外
                unique_posts = []
                seen_posts = set()
                
                for post in all_posts:
                    post_id = f"{post[0]}:{post[1][:30]}"
                    if post_id not in seen_posts:
                        unique_posts.append(post)
                        seen_posts.add(post_id)
                
                # ターゲットごとにCSVファイルを保存
                if unique_posts:
                    now = datetime.datetime.now()
                    filename = f"{data_dir}/{target_name}.csv"
                    
                    # CSVに保存
                    csv_file = scraper.save_to_csv(
                        posts=unique_posts,
                        filename=filename,
                        min_likes=min_likes
                    )
                    
                    if csv_file:
                        logger.info(f"Saved {len(unique_posts)} posts for target {target_name} to {csv_file}")
                    else:
                        logger.warning(f"Failed to save posts for target {target_name}")
                else:
                    logger.warning(f"No posts collected for target {target_name}")
        
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            logger.error(traceback.format_exc())
        
        finally:
            # スクレイパーを閉じる
            scraper.close()
    
    return data_dir

# メイン実行関数
if __name__ == "__main__":
    # .env ファイルから環境変数を明示的に読み込む
    load_dotenv(override=True)
    
    # コマンドライン引数の解析
    import argparse
    
    parser = argparse.ArgumentParser(description='Threads投稿スクレイピングツール')
    parser.add_argument('--max-posts', type=int, default=30, help='1キーワードあたりの取得する最大投稿数')
    parser.add_argument('--headless', action='store_true', help='ヘッドレスモードで実行')
    parser.add_argument('--with-images', action='store_true', help='画像付き投稿も含める')
    parser.add_argument('--min-likes', type=int, default=100, help='保存する最小いいね数（これ以下の投稿は除外）')
    parser.add_argument('--config', type=str, default='config.json', help='設定ファイルのパス')
    
    args = parser.parse_args()
    
    # configのパスをカスタマイズ可能に
    if args.config != 'config.json':
        logger.info(f"Using custom config file: {args.config}")
    
    # キーワード検索ベースでスクレイピング実行
    data_dir = scrape_threads_by_keywords(
        max_posts_per_keyword=args.max_posts,
        headless=args.headless,
        exclude_image_posts=not args.with_images,
        min_likes=args.min_likes
    )
    
    if data_dir:
        print(f"スクレイピングが完了しました。結果は {data_dir} に保存されています。")
        if args.min_likes > 0:
            print(f"いいね数が{args.min_likes}以上の投稿のみが保存されています。")
    else:
        print("スクレイピングに失敗しました。ログを確認してください。")