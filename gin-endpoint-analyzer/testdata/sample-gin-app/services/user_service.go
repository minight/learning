package services

import (
	"database/sql"
	"fmt"
)

var db *sql.DB

type User struct {
	ID       int    `json:"id"`
	Username string `json:"username"`
	Email    string `json:"email"`
	Role     string `json:"role"`
}

func GetAllUsers(page, limit string) ([]User, error) {
	// VULN: SQL injection via page and limit parameters
	query := fmt.Sprintf("SELECT id, username, email, role FROM users LIMIT %s OFFSET %s", limit, page)
	rows, err := db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var users []User
	for rows.Next() {
		var u User
		rows.Scan(&u.ID, &u.Username, &u.Email, &u.Role)
		users = append(users, u)
	}
	return users, nil
}

func FindUserByID(id string) (*User, error) {
	// VULN: SQL injection
	query := fmt.Sprintf("SELECT id, username, email, role FROM users WHERE id = %s", id)
	row := db.QueryRow(query)

	var u User
	if err := row.Scan(&u.ID, &u.Username, &u.Email, &u.Role); err != nil {
		return nil, err
	}
	return &u, nil
}

func UpdateUserFields(id string, fields map[string]interface{}) error {
	// VULN: SQL injection + mass assignment
	for key, value := range fields {
		query := fmt.Sprintf("UPDATE users SET %s = '%v' WHERE id = %s", key, value, id)
		if _, err := db.Exec(query); err != nil {
			return err
		}
	}
	return nil
}
