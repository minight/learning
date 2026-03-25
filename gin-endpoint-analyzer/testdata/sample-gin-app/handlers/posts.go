package handlers

import (
	"fmt"
	"html/template"
	"net/http"

	"github.com/gin-gonic/gin"
)

type Post struct {
	ID      int    `json:"id"`
	Title   string `json:"title"`
	Content string `json:"content"`
	UserID  int    `json:"user_id"`
}

func ListPosts(c *gin.Context) {
	category := c.Query("category")
	// VULN: SQL injection in WHERE clause
	query := fmt.Sprintf("SELECT id, title, content, user_id FROM posts WHERE category = '%s' ORDER BY id DESC", category)
	rows, err := db.Query(query)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Query failed"})
		return
	}
	defer rows.Close()

	var posts []Post
	for rows.Next() {
		var p Post
		rows.Scan(&p.ID, &p.Title, &p.Content, &p.UserID)
		posts = append(posts, p)
	}
	c.JSON(http.StatusOK, posts)
}

func CreatePost(c *gin.Context) {
	var post Post
	if err := c.ShouldBindJSON(&post); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// VULN: No input sanitization, stored XSS possible if rendered in HTML
	_, err := db.Exec("INSERT INTO posts (title, content, user_id) VALUES ($1, $2, $3)",
		post.Title, post.Content, post.UserID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, post)
}

func GetPost(c *gin.Context) {
	id := c.Param("id")
	// VULN: SQL injection
	query := fmt.Sprintf("SELECT id, title, content, user_id FROM posts WHERE id = %s", id)
	row := db.QueryRow(query)

	var post Post
	if err := row.Scan(&post.ID, &post.Title, &post.Content, &post.UserID); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Post not found"})
		return
	}
	c.JSON(http.StatusOK, post)
}

func UpdatePost(c *gin.Context) {
	id := c.Param("id")
	var post Post
	if err := c.ShouldBindJSON(&post); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	// VULN: No ownership check (IDOR), SQL injection
	query := fmt.Sprintf("UPDATE posts SET title='%s', content='%s' WHERE id = %s", post.Title, post.Content, id)
	db.Exec(query)
	c.JSON(http.StatusOK, gin.H{"message": "Updated"})
}

func DeletePost(c *gin.Context) {
	id := c.Param("id")
	// VULN: No ownership check, SQL injection
	query := fmt.Sprintf("DELETE FROM posts WHERE id = %s", id)
	db.Exec(query)
	c.JSON(http.StatusOK, gin.H{"message": "Deleted"})
}

func renderPostHTML(post Post) string {
	// VULN: XSS - directly embedding user content in HTML
	tmpl := fmt.Sprintf("<h1>%s</h1><div>%s</div>", post.Title, post.Content)
	_ = template.HTML(tmpl)
	return tmpl
}
