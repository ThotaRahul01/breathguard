 BreathGuard - Hyper-Local Air Quality Intelligence
 
 Round 2 Submission - TECHNEX'26 INNORAVE Eco-Hackathon
 BreathGuard predicts air quality in sensor blind spots using IDW spatial interpolation and Machine Learning.

Application:https://breathguard.onrender.com

 Video:https://youtu.be/YdfnQU2kPWE?si=eBT-E8SC3kENMLnL
 Google drive:https://drive.google.com/file/d/1ckDwCtx8RkJML6NmmZ0378KidA0lDTDN/view?usp=drivesdk

 Features
 Spatial Interpolation:IDW algorithm for blind spots (85% accuracy)

 24-Hour Forecast:Random Forest ML prediction

 Risk Scoring: 0-100 scale with color-coded heatmap

 Zone Analytics:Click any zone for detailed factors


 Tech Stack

 Python 3.10 + Flask
 scikit-learn (Random Forest)
 Leaflet.js + SQLite



 Installation

git clone https://github.com/ThotaRahul01/breathguard.git
 
 cd breathguard

 pip install -r requirements.txt

 python app.py

**Step 1: Clone the Repository**

git clone https://github.com/ThotaRahul01/breathguard.git

cd breathguard

**Step 2: Create Virtual Environment**

python -m venv venv

**Windows:**

venv\\Scripts\\activate

**Mac/Linux:**

source venv/bin/activate

**Step 3: Install Dependencies**

pip install -r requirements.txt

**Step 4: Run the Application**

python app.py

**Step 5: Open in Browser**

Navigate to: http://localhost:5000







