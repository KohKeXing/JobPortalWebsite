class ApplicationTracking:


    def __init__(self):

        self.applications = [

            {
                "job": "Python Developer",
                "company": "ABC Technology",
                "date": "2026-07-01",
                "status": "Interview",
                "details": "Technical interview scheduled"
            },


            {
                "job": "Software Engineer",
                "company": "XYZ Software",
                "date": "2026-06-25",
                "status": "Pending",
                "details": "Waiting for employer response"
            },


            {
                "job": "Data Analyst",
                "company": "Data Solution Sdn Bhd",
                "date": "2026-06-20",
                "status": "Rejected",
                "details": "Application unsuccessful"
            }

        ]



    # View submitted applications

    def get_applications(self):

        return self.applications



    # Update application status

    def update_status(
            self,
            index,
            new_status):


        self.applications[index]["status"] = new_status


        self.applications[index]["details"] = (
            "Status updated to "
            + new_status
        )



    # Get application details

    def get_details(
            self,
            index):

        return self.applications[index]
