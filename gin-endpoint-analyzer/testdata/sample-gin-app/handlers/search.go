package handlers

import (
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
)

func SearchHandler(c *gin.Context) {
	q := c.Query("q")
	table := c.Query("table")

	if q == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "query parameter 'q' is required"})
		return
	}

	if table == "" {
		table = "posts"
	}

	results, err := performSearch(q, table)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, results)
}

func performSearch(query string, table string) ([]map[string]interface{}, error) {
	// VULN: SQL injection via both query and table name (table name can't be parameterized)
	sqlQuery := fmt.Sprintf("SELECT * FROM %s WHERE title LIKE '%%%s%%' OR content LIKE '%%%s%%'", table, query, query)
	rows, err := db.Query(sqlQuery)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	columns, _ := rows.Columns()
	var results []map[string]interface{}
	for rows.Next() {
		values := make([]interface{}, len(columns))
		valuePtrs := make([]interface{}, len(columns))
		for i := range values {
			valuePtrs[i] = &values[i]
		}
		rows.Scan(valuePtrs...)
		row := make(map[string]interface{})
		for i, col := range columns {
			row[col] = values[i]
		}
		results = append(results, row)
	}
	return results, nil
}
