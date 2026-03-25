package main

import (
	"sample-gin-app/handlers"
	"sample-gin-app/middleware"

	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()

	// Public routes
	r.GET("/health", handlers.HealthCheck)
	r.POST("/login", handlers.Login)
	r.POST("/register", handlers.Register)

	// API v1 group
	api := r.Group("/api/v1")
	api.Use(middleware.AuthMiddleware())
	{
		// Users
		api.GET("/users", handlers.ListUsers)
		api.GET("/users/:id", handlers.GetUser)
		api.PUT("/users/:id", handlers.UpdateUser)
		api.DELETE("/users/:id", handlers.DeleteUser)

		// Posts
		api.GET("/posts", handlers.ListPosts)
		api.POST("/posts", handlers.CreatePost)
		api.GET("/posts/:id", handlers.GetPost)
		api.PUT("/posts/:id", handlers.UpdatePost)
		api.DELETE("/posts/:id", handlers.DeletePost)

		// Search
		api.GET("/search", handlers.SearchHandler)

		// File operations
		api.POST("/upload", handlers.UploadFile)
		api.GET("/files/:name", handlers.DownloadFile)

		// Admin
		admin := api.Group("/admin")
		admin.Use(middleware.AdminOnly())
		{
			admin.POST("/execute", handlers.ExecuteCommand)
			admin.GET("/logs", handlers.GetLogs)
			admin.POST("/config", handlers.UpdateConfig)
		}
	}
}
