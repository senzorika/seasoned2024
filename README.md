Sensory Evaluation Tools - Shiny Apps (created fo SEASONED Sensory Advanced Methods Summer School, Odense 2024 by Vladimir Vietoris)
This repository contains three Shiny applications designed for sensory evaluation of products: 
TCATA (Temporal Check-All-That-Apply), TDS (Temporal Dominance of Sensations), and AEF (Attribute Evolution over Time). 
These tools are used to collect and visualize sensory data over time, providing valuable insights into product attributes and consumer perception.

Applications
1. TCATA (Temporal Check-All-That-Apply)
TCATA is a method used to record multiple sensory attributes perceived simultaneously over a period of time. This Shiny app allows users to select samples, check the attributes they perceive over time, and visualize the collected data.

Features
Sample Selection: Choose from multiple samples.
Attribute Selection: Select from a predefined list of sensory attributes.
Timing: Record perceptions over a specified time range.
Save Data: Save observations and download data as an XLSX file.
Data Visualization: View attribute selection over time using histograms and perform Correspondence Analysis to explore relationships between samples and attributes.
How It Works
Users select a sample and check the attributes they perceive over time. Data is recorded by adjusting the time slider. Saved data can be visualized to understand attribute dominance and evolution over time.

2. TDS (Temporal Dominance of Sensations)
TDS focuses on capturing the most dominant sensation perceived at any given time. This Shiny app allows users to indicate the dominant sensation during the evaluation period and visualize the dominance data.

Features
Sample Selection: Choose from multiple samples.
Dominant Sensation Recording: Indicate the dominant sensation at each time point.
Save Data: Save and export observations.
Data Visualization: View dominance profiles and generate dominance curves over time.
How It Works
Users select a sample and indicate the dominant sensation they perceive at various time points during the evaluation. The app records these perceptions and generates visualizations to show the dominance of different sensations over time.

3. AEF (Attack-Evolution-Finish)
AEF tracks the evolution of specific attributes over time, allowing users to percept and write down attributes change in throughout the evaluation period.

Features
Sample Selection: Choose from multiple samples.
Attribute Intensity Recording: Record the intensity of attributes at different time points.
Save Data: Save and export recorded data.
Data Visualization: Generate and view evolution curves showing how attribute intensities change over time.
How It Works
Users select a sample and record the intensity of various attributes at specified time points. The app visualizes these intensities over time, providing insights into how attributes evolve during the evaluation.

Installation
To run these applications locally, you need to have R and the following packages installed:
install.packages(c("shiny", "shinydashboard", "ggplot2", "openxlsx", "dplyr", "tidyr", "ca"))
Usage
Clone the repository:
git clone https://github.com/yourusername/sensory-evaluation-tools.git
cd sensory-evaluation-tools
Open the respective app.R file in RStudio or your preferred R environment.

Run the application:
shiny::runApp('TCATA/app.R') # for TCATA
shiny::runApp('TDS/app.R')   # for TDS
shiny::runApp('AEF/app.R')   # for AEF
Application Structure
Each application follows a similar structure with UI and server logic defined separately:

UI: Contains user interface elements such as sample selection, attribute recording, and visualization tabs.
Server: Handles the logic for data recording, processing, and visualization.
License
This project is licensed under the MIT License - see the LICENSE file for details.

Contributing
Contributions and bugs reports are welcome! Please open an issue or submit a pull request for any changes or improvements.

Contact
For any questions or suggestions, please open an issue or contact me at vavro24@gmail.com.
