package main

import (
	"fmt"

	"github.com/acme/tool/internal/store"
)

func main() {
	s := store.New()
	s.Put("greeting", "hello")
	fmt.Println(s.Get("greeting"))
}
