// Package opendata is a rate-limited client for city open data portals
// (NYC Open Data runs on Socrata). Each city gets an adapter that maps its
// inspection records to Inspection.
package opendata

// Inspection is one violation from one restaurant inspection.
type Inspection struct {
	City           string // jurisdiction id, e.g. "us-ny-nyc"
	RestaurantID   string // NYC calls it CAMIS
	Name           string
	InspectionDate string
	ViolationCode  string
	Score          int
	Grade          string
}
