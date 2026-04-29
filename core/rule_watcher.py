"""
规则热更新监控模块
使用 watchdog 库监控规则文件变更，自动重新加载

安装依赖：
pip install watchdog
"""

from typing import Optional, Callable
from loguru import logger
import time
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog not installed, rule hot-reload disabled. Install with: pip install watchdog")


class RuleFileChangeHandler(FileSystemEventHandler):
    """规则文件变更处理器"""
    
    def __init__(
        self,
        on_change_callback: Optional[Callable] = None,
        debounce_seconds: float = 1.0
    ):
        super().__init__()
        self.on_change_callback = on_change_callback
        self.debounce_seconds = debounce_seconds
        self._last_modified: dict = {}
        self._debounce_timers: dict = {}
    
    def _should_process(self, filepath: str) -> bool:
        """判断是否应该处理该文件变更"""
        # 只处理 YAML/YML 文件
        path = Path(filepath)
        return path.suffix.lower() in ['.yaml', '.yml']
    
    def _debounce(self, filepath: str):
        """防抖处理，避免短时间内多次触发"""
        import threading
        
        # 取消之前的定时器
        if filepath in self._debounce_timers:
            self._debounce_timers[filepath].cancel()
        
        def trigger_callback():
            logger.info(f"Rule file changed: {filepath}")
            if self.on_change_callback:
                try:
                    self.on_change_callback(filepath)
                except Exception as e:
                    logger.error(f"Error in rule reload callback: {e}")
            self._debounce_timers.pop(filepath, None)
        
        # 设置新的定时器
        timer = threading.Timer(self.debounce_seconds, trigger_callback)
        self._debounce_timers[filepath] = timer
        timer.start()
    
    def on_modified(self, event):
        """文件修改事件"""
        if isinstance(event, FileModifiedEvent):
            filepath = event.src_path
            if self._should_process(filepath):
                self._debounce(filepath)
    
    def on_created(self, event):
        """文件创建事件"""
        filepath = event.src_path
        if self._should_process(filepath):
            logger.info(f"New rule file created: {filepath}")
            self._debounce(filepath)


class RuleHotReloader:
    """
    规则热更新管理器
    监控规则目录，文件变更时自动触发重新加载
    """
    
    def __init__(
        self,
        rules_dir: str,
        reload_callback: Optional[Callable] = None,
        debounce_seconds: float = 1.0
    ):
        """
        Args:
            rules_dir: 规则文件目录
            reload_callback: 文件变更时的回调函数（接收文件路径）
            debounce_seconds: 防抖时间（秒）
        """
        self.rules_dir = Path(rules_dir)
        self.reload_callback = reload_callback
        self.debounce_seconds = debounce_seconds
        self._observer: Optional[Observer] = None
        self._is_running = False
    
    def start(self):
        """启动监控"""
        if not WATCHDOG_AVAILABLE:
            logger.warning("Cannot start rule watcher: watchdog not installed")
            return False
        
        if self._is_running:
            logger.debug("Rule watcher already running")
            return True
        
        try:
            # 确保目录存在
            self.rules_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建处理器
            handler = RuleFileChangeHandler(
                on_change_callback=self.reload_callback,
                debounce_seconds=self.debounce_seconds
            )
            
            # 创建观察者
            self._observer = Observer()
            self._observer.schedule(
                handler,
                str(self.rules_dir),
                recursive=False  # 只监控根目录，不监控子目录
            )
            
            # 启动
            self._observer.start()
            self._is_running = True
            
            logger.info(f"Rule hot-reload started, watching: {self.rules_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start rule watcher: {e}")
            return False
    
    def stop(self):
        """停止监控"""
        if self._observer and self._is_running:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._is_running = False
            logger.info("Rule hot-reload stopped")
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._is_running


# ==================== 使用示例 ====================
if __name__ == "__main__":
    import asyncio
    from .triage import IntelligentTriage
    
    async def test_hot_reload():
        # 创建分诊器
        triage = IntelligentTriage(rules_dir="/data01/shenxf/Agent/medical-agent/rules")
        
        # 定义重载回调
        def on_rules_reload(filepath):
            logger.info(f"Reloading rules from: {filepath}")
            triage.rule_engine.load_rules(force=True)
            logger.info("Rules reloaded successfully")
        
        # 启动热更新监控
        reloader = RuleHotReloader(
            rules_dir="/data01/shenxf/Agent/medical-agent/rules",
            reload_callback=on_rules_reload,
            debounce_seconds=1.0
        )
        reloader.start()
        
        # 示例患者数据
        patient = {
            "age": 35,
            "gender": "male",
            "bmi": 29.5,
            "labs": {"ALT": 65, "AST": 48},
            "ultrasound": {"findings": "肝回声增强"}
        }
        
        # 第一次分诊
        result1 = await triage.triage(patient)
        print(f"First triage: {result1.diagnosis}")
        
        # 等待规则文件变更（手动修改 YAML 文件测试）
        print("Waiting for rule file changes... (modify rules/*.yaml to test)")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            reloader.stop()
            print("Stopped")
    
    # asyncio.run(test_hot_reload())
