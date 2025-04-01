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
    
    def _wait_for_content_load(self, timeout=8):  # タイムアウトを延長
        """
        コンテンツが読み込まれるのを待つ
        
        Args:
            timeout (int): 最大待機時間（秒）
            
        Returns:
            bool: 読み込みが完了したかどうか
        """
        try:
            # document.readyStateを確認
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # スピナーや読み込み中の要素を検出（Threadsの場合）
            loading_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[role='progressbar']")
            if loading_elements:
                # 読み込み中要素が消えるのを待つ
                WebDriverWait(self.driver, timeout).until_not(
                    lambda d: d.find_elements(By.CSS_SELECTOR, "div[role='progressbar']")
                )
            
            return True
        except:
            logger.warning(f"Content load wait timed out after {timeout} seconds")
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
        Threadsにログインする
        """
        try:
            # 直接ログインページにアクセス
            self.driver.get("https://www.threads.net/login")
            logger.info("Navigated to direct login URL: https://www.threads.net/login")
            self._wait_for_page_load(20)  # ページのロードを十分待つ
            
            # 人間らしい遅延
            self._human_like_delay(3.0, 5.0)
            
            # デバッグ用にスクリーンショット保存
            self.driver.save_screenshot("login_page.png")
            logger.info("Saved screenshot of login page")
            
            # 日本語プレースホルダーに基づいたXPathセレクタ
            username_xpath = "//input[@placeholder='ユーザーネーム、携帯電話番号、またはメールアドレス']"
            
            # CSSセレクタの方法（autocomplete属性を使用）
            username_css = "input[autocomplete='username']"
            
            # ユーザー名入力欄を見つける
            try:
                # 複数の方法で検索
                username_selectors = [
                    username_xpath,
                    username_css,
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
                    # 全ての入力フィールドを探す最終手段
                    inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    for inp in inputs:
                        if inp.get_attribute("type") == "text":
                            username_field = inp
                            logger.info("Username field found by searching all input fields")
                            break
                
                if not username_field:
                    logger.error("Could not find username field")
                    return False
                
                # 人間らしいタイピングでユーザー名を入力
                self._human_like_typing(username_field, username)
                logger.info(f"Successfully entered username: {username}")
                
                # Enterキーを押す前に少し待機
                self._human_like_delay(1.0, 2.0)
                
                # パスワード入力欄を見つける
                password_css = "input[type='password']"
                password_field = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, password_css))
                )
                
                # 人間らしいタイピングでパスワードを入力
                self._human_like_typing(password_field, password)
                logger.info("Password entered successfully")
                
                # ログインボタンを見つける
                try:
                    login_button_selectors = [
                        "//div[contains(text(), 'ログイン') and @role='button']",
                        "//div[@role='button']//div[contains(@class, 'xwhw2v2')]",
                        "div.x1i10hfl[role='button']"
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
                    
                    if login_button:
                        # 人間らしいクリック
                        self._safe_click(login_button)
                        logger.info("Login button clicked")
                    else:
                        # ボタンが見つからない場合はエンターキーを押す
                        self._human_like_delay(0.5, 1.0)
                        password_field.send_keys(Keys.RETURN)
                        logger.info("Pressed Enter key to submit login form")
                except Exception as e:
                    logger.warning(f"Could not find login button: {e}")
                    # ログインボタンが見つからない場合はエンターキーを押す
                    self._human_like_delay(0.5, 1.0)
                    password_field.send_keys(Keys.RETURN)
                    logger.info("Pressed Enter key to submit login form")
                
                # ログイン完了を待機
                self._human_like_delay(5.0, 8.0)
                
                # ログイン成功の確認
                if "login" not in self.driver.current_url.lower():
                    logger.info(f"Login successful! Current URL: {self.driver.current_url}")
                    return True
                else:
                    logger.warning(f"Still on login page after login attempt: {self.driver.current_url}")
                    return False
                
            except Exception as e:
                logger.error(f"Error during login form interaction: {e}")
                logger.error(traceback.format_exc())
                # スクリーンショットを保存
                self.driver.save_screenshot("login_error.png")
                logger.info("Saved screenshot of login error")
                return False
            
        except Exception as e:
            logger.error(f"Error during login: {e}")
            logger.error(traceback.format_exc())
            return False
    
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
        強制的に画面の最下部までスクロールする
        
        Returns:
            bool: スクロールが成功したかどうか
        """
        try:
            # 現在の高さを取得
            current_height = self.driver.execute_script("return window.innerHeight")
            page_height = self.driver.execute_script("return document.body.scrollHeight")
            logger.info(f"Current view height: {current_height}, Total page height: {page_height}")
            
            # ページの最下部まで強制的にスクロール
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            logger.info("Forced scroll to bottom of page")
            
            # スクロール後の適切な待機
            self._human_like_delay(3.0, 5.0)
            
            # スクロール後の高さを確認
            new_page_height = self.driver.execute_script("return document.body.scrollHeight")
            logger.info(f"After forced scroll - Page height: {new_page_height}")
            
            # スクロールが成功したかどうかを返す
            return new_page_height > page_height
            
        except Exception as e:
            logger.error(f"Error during force scroll: {e}")
            return False

    def _check_end_of_feed(self):
        """
        フィードの終わりに達したかどうかを確認する
        
        Returns:
            bool: フィードの終わりに達した場合はTrue
        """
        # 「これ以上の投稿はありません」などのメッセージを検出
        end_messages = [
            "これ以上の投稿はありません", 
            "No more posts", 
            "End of feed",
            "すべての投稿を見ました"
        ]
        
        page_source = self.driver.page_source.lower()
        for message in end_messages:
            if message.lower() in page_source:
                logger.info(f"End of feed detected: '{message}'")
                return True
        
        # 特定のセレクタで終わりを示す要素を検出
        end_selectors = [
            "div[role='button'][aria-label*='refresh']",
            "div.x1lliihq",  # Threadsの「終わり」を示す可能性のあるクラス
            "svg[aria-label*='refresh']"
        ]
        
        for selector in end_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.info(f"End indicator found with selector: {selector}")
                    return True
            except:
                continue
        
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

    def extract_posts(self, max_posts=100, exclude_image_posts=True):
        """
        投稿を抽出する関数（大幅改良版）
        """
        posts = []
        processed_post_ids = set()
        retry_count = 0
        max_retries = 20  # より多くの再試行を許可
        no_new_posts_count = 0
        max_no_new_posts = 5
        
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
            
            while len(posts) < max_posts and retry_count < max_retries:
                # 現在の投稿数をログに記録
                logger.info(f"Current post count: {len(posts)}/{max_posts}, Retry: {retry_count+1}/{max_retries}")
                
                # 一定回数試行してもうまくいかない場合は、別のスクロール方法を試す
                if retry_count % 4 == 0:
                    logger.info("Using progressive scroll technique...")
                    new_posts_added = self._progressive_scroll(8)  # 段階的スクロールを実行
                    if new_posts_added == 0:
                        logger.warning("Progressive scroll didn't add any new posts")
                        
                        # ここで強制的にページ最下部までスクロール
                        logger.info("Forcing scroll to bottom...")
                        self._force_scroll_to_bottom()
                        self._human_like_delay(5.0, 7.0)
                
                # 一定間隔でページを更新
                if no_new_posts_count >= 3 and retry_count % 3 == 0:
                    logger.info("Refreshing page to get new content...")
                    current_url = self.driver.current_url
                    self.driver.get(current_url)
                    self._human_like_delay(5.0, 8.0)
                    self._wait_for_content_load(10)
                    processed_post_ids.clear()  # 処理済み投稿IDをリセット
                
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
                                    except:
                                        container_id = hash(str(container.location))
                                    
                                    # 既に処理済みの投稿はスキップ
                                    if container_id in processed_post_ids:
                                        continue
                                    
                                    processed_post_ids.add(container_id)
                                    
                                    # 画像の存在をチェック（exclude_image_posts がTrueの場合）
                                    if exclude_image_posts:
                                        try:
                                            # img要素を探す
                                            images = container.find_elements(By.TAG_NAME, "img")
                                            # 投稿内の画像数をカウント（プロフィール画像は除外）
                                            post_images = [img for img in images if not any(attr in (img.get_attribute("alt") or "").lower() for attr in ["profile", "プロフィール", "アバター", "avatar"])]
                                            
                                            # 画像が含まれている場合はスキップ
                                            if len(post_images) > 1:  # 1つ目はプロフィール画像かもしれないので、2枚以上ある場合
                                                logger.info("Post contains images, skipping...")
                                                continue
                                        except Exception as e:
                                            logger.warning(f"Error checking for images: {e}")
                                    
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
            if no_new_posts_count >= 3 and retry_count % 5 == 0:
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

# 複数アカウントでThreadsのタイムラインから投稿を取得し、単一のCSVファイルに保存する関数
def scrape_threads_with_multiple_accounts(accounts, max_posts_per_account=30, headless=False, exclude_image_posts=True, min_likes=500):
    """
    複数のアカウントを使ってThreadsのタイムラインから投稿を取得する関数（ログイン処理を強化）
    
    Args:
        accounts (list): ユーザー名とパスワードのタプルのリスト [(username1, password1), (username2, password2), ...]
        max_posts_per_account (int): アカウントごとに取得する最大投稿数
        headless (bool): ヘッドレスモードで実行するかどうか
        exclude_image_posts (bool): 画像を含む投稿を除外するかどうか
        min_likes (int): 保存する最小いいね数（デフォルトは500）
    
    Returns:
        str: 保存されたCSVファイルのパス
    """
    all_posts = []
    csv_filename = f"threads_posts_{datetime.datetime.now().strftime('%m%d_%H%M')}.csv"
    
    # アカウント情報のチェック（デバッグ用）
    for i, (username, password) in enumerate(accounts):
        if username and password:
            logger.info(f"Account {i+1}: Username provided ({len(username)} chars), Password provided ({len(password)} chars)")
        else:
            logger.warning(f"Account {i+1}: Missing {'username' if not username else ''} {'password' if not password else ''}")
    
    account_count = len(accounts)
    for i, (username, password) in enumerate(accounts, 1):
        logger.info(f"Starting scraping with account {i}/{account_count}: {username or '[No username provided]'}")
        scraper = ThreadsScraper(headless=headless)
        
        try:
            # ログイン情報があるか確認
            if username and password:
                logger.info(f"Attempting to login with username: {username}")
                # 最初にログインページに直接アクセス
                scraper.driver.get("https://www.threads.net/login")
                logger.info("Navigated to direct login URL: https://www.threads.net/login")
                scraper._wait_for_page_load()
                
                # ログイン処理
                login_success = scraper.login(username, password)
                if login_success:
                    logger.info("Login successful! Proceeding to scrape timeline.")
                    # ログイン成功後、タイムラインに移動
                    scraper.navigate_to_threads()
                else:
                    logger.warning("Login failed. Attempting to scrape without login.")
                    # ログイン失敗時もタイムラインに移動
                    scraper.navigate_to_threads()
            else:
                logger.warning("No login credentials provided. Scraping without login.")
                # ログイン情報がない場合、直接タイムラインに移動
                scraper.navigate_to_threads()
            
            # 投稿を取得
            posts = scraper.extract_posts(max_posts=max_posts_per_account, exclude_image_posts=exclude_image_posts)
            all_posts.extend(posts)
            
            logger.info(f"Collected {len(posts)} posts with account {i}")
            
        except Exception as e:
            logger.error(f"Error during scraping with account {username}: {e}")
            logger.error(traceback.format_exc())
        finally:
            # 必ずスクレイパーを閉じる
            scraper.close()
    
    # すべてのデータを一つのCSVファイルに保存
    if all_posts:
        # 重複の削除とCSV保存
        unique_posts = []
        seen_post_identifiers = set()
        
        for username, post_text, likes in all_posts:
            # ユーザー名と投稿内容の最初の部分で一意性を確保
            post_id = f"{username}:{post_text[:30]}"
            if post_id not in seen_post_identifiers:
                unique_posts.append((username, post_text, likes))
                seen_post_identifiers.add(post_id)
        
        # データフレームを作成して保存
        df = pd.DataFrame(unique_posts, columns=["username", "post_text", "likes"])
        
        # 元のCSVファイルを保存
        df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
        logger.info(f"Saved a total of {len(unique_posts)} unique posts to {csv_filename}")
        
        # いいね数でフィルタリング
        if min_likes > 0:
            filtered_df = df[df['likes'] > min_likes]
            filtered_count = len(filtered_df)
            
            # フィルター後のファイル名を生成
            filtered_filename = csv_filename.replace('.csv', f'_likes{min_likes}plus.csv')
            
            # フィルター後のデータを保存
            filtered_df.to_csv(filtered_filename, index=False, encoding='utf-8-sig')
            logger.info(f"Filtered to {filtered_count} posts with more than {min_likes} likes in {filtered_filename}")
            
            # 削除された投稿数を表示
            removed_count = len(df) - filtered_count
            logger.info(f"Removed {removed_count} posts with {min_likes} or fewer likes")
            
            return filtered_filename
        
        return csv_filename
    else:
        logger.warning("No posts were collected from any account")
        return None

def scrape_threads_posts(max_posts=100, headless=False, exclude_image_posts=True, min_likes=500):
    """
    Threadsから投稿をスクレイピングする関数（main.pyとの互換性のため）
    
    Args:
        max_posts (int): 1アカウントあたりの最大取得投稿数
        headless (bool): ヘッドレスモードで実行するかどうか
        exclude_image_posts (bool): 画像付き投稿を除外するかどうか
        min_likes (int): フィルタリングするいいねの最小数
        
    Returns:
        str: 保存したCSVファイルのパス、または失敗時はNone
    """
    # .envファイルからアカウント情報を取得
    accounts = get_accounts_from_env()
    
    if not accounts:
        logger.warning("アカウント情報が見つかりません。ログインなしでスクレイピングを試みます。")
        accounts = [("", "")]  # 空のログイン情報
    
    # スクレイピング実行（1アカウントあたり30投稿に制限）
    return scrape_threads_with_multiple_accounts(
        accounts=accounts,
        max_posts_per_account=max_posts,  # mainからのmax_postsをそのまま使用
        headless=headless,
        exclude_image_posts=exclude_image_posts,
        min_likes=min_likes
    )

# メイン実行関数
if __name__ == "__main__":
    # .env ファイルから環境変数を明示的に読み込む
    load_dotenv(override=True)
    
    # コマンドライン引数の解析
    import argparse
    
    parser = argparse.ArgumentParser(description='Threads投稿スクレイピングツール')
    parser.add_argument('--max-posts', type=int, default=100, help='取得する最大投稿数')
    parser.add_argument('--headless', action='store_true', help='ヘッドレスモードで実行')
    parser.add_argument('--with-images', action='store_true', help='画像付き投稿も含める')
    parser.add_argument('--min-likes', type=int, default=500, help='保存する最小いいね数（これ以下の投稿は除外）')
    parser.add_argument('--username', type=str, help='Threadsにログインするためのユーザー名')
    parser.add_argument('--password', type=str, help='Threadsにログインするためのパスワード')
    parser.add_argument('--login-required', action='store_true', help='ログイン必須モード（ログインが失敗した場合はスクレイピングを中止）')
    
    args = parser.parse_args()
    
    # コマンドライン引数のログイン情報を優先
    if args.username and args.password:
        accounts = [(args.username, args.password)]
        print(f"コマンドライン引数からログイン情報を取得しました: {args.username}")
    else:
        # .env ファイルからアカウント情報を取得
        accounts = get_accounts_from_env()
    
    if not accounts:
        print("警告: ログイン情報が見つかりません。ログインなしでスクレイピングを試みます。")
        if args.login_required:
            print("エラー: ログイン必須モードが指定されていますが、ログイン情報が提供されていません。")
            sys.exit(1)
        accounts = [("", "")]  # 空のログイン情報
    else:
        print(f"{len(accounts)}個のアカウント情報が見つかりました。")
    
    # スクレイピング実行
    csv_file = scrape_threads_posts(
        max_posts=args.max_posts,
        headless=args.headless,
        exclude_image_posts=not args.with_images,
        min_likes=args.min_likes
    )
    
    if csv_file:
        print(f"スクレイピングが完了しました。結果は {csv_file} に保存されています。")
        if args.min_likes > 0:
            print(f"いいね数が{args.min_likes}を超える投稿のみが保存されています。")
    else:
        print("スクレイピングに失敗しました。ログを確認してください。")