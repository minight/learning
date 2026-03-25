package handlers

import (
	"net/http"
	"runtime"

	"github.com/gin-gonic/gin"
)

func HealthCheck(c *gin.Context) {
	// INFO: Exposes runtime information
	c.JSON(http.StatusOK, gin.H{
		"status":     "ok",
		"go_version": runtime.Version(),
		"goroutines": runtime.NumGoroutine(),
		"os":         runtime.GOOS,
		"arch":       runtime.GOARCH,
	})
}
