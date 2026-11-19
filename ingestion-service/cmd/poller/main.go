// Command poller checks each city's open data portal on a schedule for new
// restaurant inspection results and publishes an inspections.new event to
// Kafka for each one (weeks 5 to 6).
package main

import (
	"log"
	"os"
)

func main() {
	cities := os.Getenv("CITIES")
	if cities == "" {
		cities = "us-ny-nyc"
	}
	log.Printf("poller: not implemented yet (weeks 5 to 6), cities=%s", cities)
}
