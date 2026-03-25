package handlers

import (
	"database/sql"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
)

var db *sql.DB

func Login(c *gin.Context) {
	username := c.PostForm("username")
	password := c.PostForm("password")

	// VULN: SQL Injection - string concatenation in query
	query := fmt.Sprintf("SELECT id, role FROM users WHERE username='%s' AND password='%s'", username, password)
	row := db.QueryRow(query)

	var id int
	var role string
	if err := row.Scan(&id, &role); err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid credentials"})
		return
	}

	token := generateToken(id, role)
	c.JSON(http.StatusOK, gin.H{"token": token})
}

func Register(c *gin.Context) {
	username := c.PostForm("username")
	password := c.PostForm("password")
	email := c.PostForm("email")

	// VULN: SQL Injection via string formatting
	query := fmt.Sprintf("INSERT INTO users (username, password, email) VALUES ('%s', '%s', '%s')", username, password, email)
	_, err := db.Exec(query)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()}) // VULN: error info disclosure
		return
	}

	c.JSON(http.StatusCreated, gin.H{"message": "User created"})
}

func generateToken(userID int, role string) string {
	// VULN: Weak token generation, hardcoded secret
	secret := "mysecretkey123"
	return fmt.Sprintf("%d:%s:%s", userID, role, secret)
}
