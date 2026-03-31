package counter

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
)

type Counter struct {
	value atomic.Int64
	path  string
}

func New(path string) (*Counter, error) {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, fmt.Errorf("creating counter directory: %w", err)
	}

	c := &Counter{path: path}

	data, err := os.ReadFile(path)
	if err == nil {
		v, err := strconv.ParseInt(strings.TrimSpace(string(data)), 10, 64)
		if err == nil && v > 0 {
			c.value.Store(v)
		}
	}

	return c, nil
}

func (c *Counter) Increment() int64 {
	v := c.value.Add(1)
	c.persist(v)
	return v
}

func (c *Counter) Value() int64 {
	return c.value.Load()
}

func (c *Counter) persist(v int64) {
	_ = os.WriteFile(c.path, []byte(strconv.FormatInt(v, 10)+"\n"), 0644)
}
