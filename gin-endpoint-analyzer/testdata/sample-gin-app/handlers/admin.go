package handlers

import (
	"io/ioutil"
	"net/http"
	"os"
	"os/exec"

	"github.com/gin-gonic/gin"
)

func ExecuteCommand(c *gin.Context) {
	var body struct {
		Command string `json:"command"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// VULN: Command injection - executing user-supplied command
	out, err := exec.Command("sh", "-c", body.Command).CombinedOutput()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":  err.Error(),
			"output": string(out),
		})
		return
	}
	c.JSON(http.StatusOK, gin.H{"output": string(out)})
}

func GetLogs(c *gin.Context) {
	logFile := c.Query("file")
	if logFile == "" {
		logFile = "/var/log/app.log"
	}

	// VULN: Path traversal - no validation on file path
	data, err := ioutil.ReadFile(logFile)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.String(http.StatusOK, string(data))
}

func UpdateConfig(c *gin.Context) {
	var body struct {
		Key   string `json:"key"`
		Value string `json:"value"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// VULN: Arbitrary file write via config key as path
	configPath := "/etc/app/config/" + body.Key
	err := os.WriteFile(configPath, []byte(body.Value), 0644)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "Config updated"})
}
