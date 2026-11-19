// Package publisher sends inspection events to Kafka (or a managed Kafka such as MSK).
package publisher

// InspectionNewEvent is the payload on the inspections.new topic. City, RestaurantID,
// InspectionDate and ViolationCode together are the idempotency key.
type InspectionNewEvent struct {
	City           string `json:"city"`
	RestaurantID   string `json:"restaurant_id"`
	InspectionDate string `json:"inspection_date"`
	ViolationCode  string `json:"violation_code"`
	Score          int    `json:"score"`
	Grade          string `json:"grade"`
	SourceURL      string `json:"source_url"`
}
