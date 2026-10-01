package store

import "sync"

// Store is a concurrency-safe key/value map.
type Store struct {
	mu   sync.RWMutex
	data map[string]string
}

// New creates an empty Store.
func New() *Store {
	return &Store{data: map[string]string{}}
}

// Get returns the value for key.
func (s *Store) Get(key string) string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.data[key]
}

// Put stores value under key.
func (s *Store) Put(key, value string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data[key] = value
}
