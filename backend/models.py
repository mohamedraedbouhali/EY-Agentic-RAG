# MongoDB — no ORM models needed.
# Documents in the "users" collection follow this shape:
#
# {
#   "_id":             ObjectId,
#   "email":           str  (unique),
#   "hashed_password": str,
#   "first_name":      str,
#   "last_name":       str,
#   "role_title":      str,   # Consultant, Manager, etc.
#   "role":            str,   # "admin" | "user"
#   "is_approved":     bool,
#   "created_at":      datetime,
# }
