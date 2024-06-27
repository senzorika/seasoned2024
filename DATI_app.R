# SEASONED Sensory summer school, SDU Odense, Denmark
# Vladimir Vietoris, 2024
# Install and load necessary packages
if (!require(shiny)) install.packages("shiny")
if (!require(ggplot2)) install.packages("ggplot2")
if (!require(openxlsx)) install.packages("openxlsx")

library(shiny)
library(ggplot2)
library(openxlsx)

# Define the user interface
ui <- navbarPage(
  title = "DATI Analysis",
  tabPanel("Data Collection",
           sidebarLayout(
             sidebarPanel(
               numericInput("time_points", "Analysis Duration (seconds)", 30, min = 1),
               textInput("attribute1", "Attribute 1", "Sweetness"),
               textInput("attribute2", "Attribute 2", "Bitterness"),
               actionButton("start", "Start Measurement"),
               actionButton("stop", "Stop Measurement"),
               sliderInput("intensity1", "Intensity of Attribute 1", min = 1, max = 10, value = 1),
               sliderInput("intensity2", "Intensity of Attribute 2", min = 1, max = 10, value = 1),
               textOutput("runningTime")
             ),
             mainPanel(
               plotOutput("livePlot")
             )
           )),
  tabPanel("Results Visualization",
           sidebarLayout(
             sidebarPanel(
               downloadButton("downloadData", "Download Data")
             ),
             mainPanel(
               plotOutput("finalPlot"),
               plotOutput("ratioPlot")
             )
           ))
)

# Define the server logic
server <- function(input, output, session) {
  values <- reactiveValues(
    time = numeric(0),
    intensity1 = numeric(0),
    intensity2 = numeric(0),
    timer = NULL,
    running = FALSE
  )
  
  observeEvent(input$start, {
    values$time <- numeric(0)
    values$intensity1 <- numeric(0)
    values$intensity2 <- numeric(0)
    values$timer <- 0
    values$running <- TRUE
    
    updateSliderInput(session, "intensity1", value = 1)
    updateSliderInput(session, "intensity2", value = 1)
    
    invalidateLater(1000, session)
  })
  
  observe({
    if (values$running) {
      isolate({
        values$time <- c(values$time, values$timer)
        values$intensity1 <- c(values$intensity1, input$intensity1)
        values$intensity2 <- c(values$intensity2, input$intensity2)
        values$timer <- values$timer + 1
      })
      if (values$timer <= input$time_points) {
        invalidateLater(1000, session)
      } else {
        values$running <- FALSE
      }
    }
  })
  
  observeEvent(input$stop, {
    values$running <- FALSE
  })
  
  output$runningTime <- renderText({
    if (values$running) {
      paste("Running Time: ", values$timer, "seconds")
    } else if (values$timer > 0) {
      paste("Measurement Completed at ", values$timer, "seconds")
    } else {
      "Measurement Stopped"
    }
  })
  
  output$livePlot <- renderPlot({
    if (length(values$time) > 0) {
      data <- data.frame(
        Time = rep(values$time, 2),
        Intensity = c(values$intensity1, values$intensity2),
        Attribute = rep(c(input$attribute1, input$attribute2), each = length(values$time))
      )
      
      ggplot(data, aes(x = Time, y = Intensity, color = Attribute, group = Attribute)) +
        geom_line(size = 1) +
        geom_point(size = 2) +
        labs(title = "Live DATI Graph",
             x = "Time (seconds)",
             y = "Intensity") +
        theme_minimal()
    }
  })
  
  output$finalPlot <- renderPlot({
    if (length(values$time) > 0) {
      data <- data.frame(
        Time = rep(values$time, 2),
        Intensity = c(values$intensity1, values$intensity2),
        Attribute = rep(c(input$attribute1, input$attribute2), each = length(values$time))
      )
      
      ggplot(data, aes(x = Time, y = Intensity, color = Attribute, group = Attribute)) +
        geom_line(size = 1) +
        geom_point(size = 2) +
        labs(title = "Final DATI Graph",
             x = "Time (seconds)",
             y = "Intensity") +
        theme_minimal()
    }
  })
  
  output$ratioPlot <- renderPlot({
    if (length(values$time) > 0) {
      ratio_data <- data.frame(
        Attribute = c(input$attribute1, input$attribute2),
        MeanIntensity = c(mean(values$intensity1), mean(values$intensity2))
      )
      
      ggplot(ratio_data, aes(x = Attribute, y = MeanIntensity, fill = Attribute)) +
        geom_bar(stat = "identity") +
        labs(title = "Ratio of Mean Intensities",
             x = "Attribute",
             y = "Mean Intensity") +
        theme_minimal()
    }
  })
  
  output$downloadData <- downloadHandler(
    filename = function() {
      paste("DATI_data_", Sys.Date(), ".xlsx", sep = "")
    },
    content = function(file) {
      if (length(values$time) > 0) {
        data <- data.frame(
          Time = values$time,
          Intensity1 = values$intensity1,
          Intensity2 = values$intensity2,
          Attribute1 = input$attribute1,
          Attribute2 = input$attribute2
        )
        write.xlsx(data, file)
      }
    }
  )
}

# Spuštění aplikace Shiny
shinyApp(ui = ui, server = server)