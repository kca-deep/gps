"""
캐시 유틸리티

메모리 기반의 간단한 캐시 시스템
TTL(Time To Live) 지원 및 LRU(Least Recently Used) 정책 구현
"""

import time
import threading
from typing import Any, Optional, Dict, Tuple
from collections import OrderedDict
import logging


class SimpleCache:
    """간단한 메모리 기반 캐시 클래스"""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """
        캐시 초기화
        
        Args:
            max_size: 최대 캐시 항목 수
            ttl_seconds: 기본 TTL (초)
        """
        self.max_size = max_size
        self.default_ttl = ttl_seconds
        self._cache: OrderedDict = OrderedDict()  # {key: (value, expire_time)}
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        
        # 통계 정보
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        캐시에서 값 조회
        
        Args:
            key: 캐시 키
            
        Returns:
            캐시된 값 또는 None
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, expire_time = self._cache[key]
            
            # TTL 확인
            if time.time() > expire_time:
                del self._cache[key]
                self._misses += 1
                return None
            
            # LRU 업데이트 (맨 뒤로 이동)
            self._cache.move_to_end(key)
            self._hits += 1
            
            return value
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """
        캐시에 값 저장
        
        Args:
            key: 캐시 키
            value: 저장할 값
            ttl_seconds: TTL (초), None이면 기본값 사용
        """
        with self._lock:
            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
            expire_time = time.time() + ttl
            
            # 기존 키가 있으면 업데이트
            if key in self._cache:
                self._cache[key] = (value, expire_time)
                self._cache.move_to_end(key)
                return
            
            # 새 키 추가
            self._cache[key] = (value, expire_time)
            
            # 최대 크기 초과 시 오래된 항목 제거
            while len(self._cache) > self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
    
    def delete(self, key: str) -> bool:
        """
        캐시에서 키 삭제
        
        Args:
            key: 삭제할 키
            
        Returns:
            삭제 성공 여부
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """캐시 전체 비우기"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def cleanup_expired(self) -> int:
        """
        만료된 항목들 정리
        
        Returns:
            삭제된 항목 수
        """
        with self._lock:
            current_time = time.time()
            expired_keys = []
            
            for key, (value, expire_time) in self._cache.items():
                if current_time > expire_time:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                self.logger.debug(f"캐시 정리: {len(expired_keys)}개 항목 삭제")
            
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        캐시 통계 정보 반환
        
        Returns:
            통계 정보 딕셔너리
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 2),
                'total_items': len(self._cache),
                'max_size': self.max_size,
                'default_ttl': self.default_ttl
            }
    
    def get_size(self) -> int:
        """현재 캐시 크기 반환"""
        with self._lock:
            return len(self._cache)
    
    def exists(self, key: str) -> bool:
        """
        키가 존재하고 만료되지 않았는지 확인
        
        Args:
            key: 확인할 키
            
        Returns:
            존재 여부
        """
        return self.get(key) is not None


class CacheManager:
    """캐시 관리자 클래스"""
    
    def __init__(self):
        """캐시 매니저 초기화"""
        self._caches: Dict[str, SimpleCache] = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
    
    def get_cache(self, name: str, max_size: int = 1000, ttl_seconds: int = 300) -> SimpleCache:
        """
        이름으로 캐시 인스턴스 조회/생성
        
        Args:
            name: 캐시 이름
            max_size: 최대 크기 (새 캐시 생성 시)
            ttl_seconds: 기본 TTL (새 캐시 생성 시)
            
        Returns:
            캐시 인스턴스
        """
        with self._lock:
            if name not in self._caches:
                self._caches[name] = SimpleCache(max_size, ttl_seconds)
                self.logger.debug(f"새 캐시 생성: {name}")
            
            return self._caches[name]
    
    def cleanup_all_expired(self) -> Dict[str, int]:
        """
        모든 캐시의 만료된 항목들 정리
        
        Returns:
            캐시별 삭제된 항목 수
        """
        with self._lock:
            cleanup_results = {}
            
            for name, cache in self._caches.items():
                deleted_count = cache.cleanup_expired()
                cleanup_results[name] = deleted_count
            
            return cleanup_results
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        모든 캐시의 통계 정보 반환
        
        Returns:
            캐시별 통계 정보
        """
        with self._lock:
            stats = {}
            
            for name, cache in self._caches.items():
                stats[name] = cache.get_stats()
            
            return stats
    
    def clear_cache(self, name: str) -> bool:
        """
        특정 캐시 비우기
        
        Args:
            name: 캐시 이름
            
        Returns:
            성공 여부
        """
        with self._lock:
            if name in self._caches:
                self._caches[name].clear()
                return True
            return False
    
    def clear_all_caches(self) -> None:
        """모든 캐시 비우기"""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()
    
    def remove_cache(self, name: str) -> bool:
        """
        캐시 인스턴스 제거
        
        Args:
            name: 제거할 캐시 이름
            
        Returns:
            제거 성공 여부
        """
        with self._lock:
            if name in self._caches:
                del self._caches[name]
                self.logger.debug(f"캐시 제거: {name}")
                return True
            return False


# 전역 캐시 매니저 인스턴스
cache_manager = CacheManager()


def get_cache_manager() -> CacheManager:
    """전역 캐시 매니저 반환"""
    return cache_manager


# 자동 정리 스레드 (백그라운드에서 주기적으로 만료된 항목 정리)
import atexit


def _cleanup_thread():
    """백그라운드 정리 스레드"""
    import time
    import threading
    
    def cleanup_worker():
        while not _cleanup_shutdown_event.is_set():
            try:
                cache_manager.cleanup_all_expired()
                # 5분마다 정리
                _cleanup_shutdown_event.wait(300)
            except Exception as e:
                logging.getLogger(__name__).error(f"캐시 정리 중 오류: {e}")
    
    _cleanup_shutdown_event = threading.Event()
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    
    # 프로그램 종료 시 정리 스레드도 종료
    def stop_cleanup():
        _cleanup_shutdown_event.set()
    
    atexit.register(stop_cleanup)
    
    return _cleanup_shutdown_event


# 정리 스레드 시작
_cleanup_shutdown_event = _cleanup_thread() 