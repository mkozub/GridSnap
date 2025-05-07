# GridSnap

A Python web application that uses Google's Gemini Vision AI to extract data from screenshots of tables and imports it directly into Smartsheet.

## What It Does

GridSnap bridges the gap between visual data and Smartsheet by:
- Using Gemini AI to identify and extract table structures from images
- Automatically detecting column headers and data types
- Formatting and transferring the extracted data to Smartsheet
- Providing a simple browser-based interface for the entire process

## Features

- Upload screenshots of tables (Excel, PDFs, etc.)
- Verify Smartsheet ID and connection
- Extract column headers and row data
- Preview data before pushing to Smartsheet
- Clean interface with drag-and-drop support

## Prerequisites

- Python 3.7 or higher
- Google Gemini API key - [Get it here](https://ai.google.dev/)
- Smartsheet API token - Available in your Smartsheet account under Account > Personal Settings > API Access

## Setup

1. **Clone the repository**

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   - Copy `.env.template` to `.env`
   - Add your API keys:
     ```
     GEMINI_API_KEY=your_gemini_api_key_here
     SMARTSHEET_API_TOKEN=your_smartsheet_api_token_here
     ```

5. **Run the application**
   ```bash
   python main.py
   ```

6. **Access the app**
   - Open [http://localhost:5001](http://localhost:5001)

## Usage Guide

1. Enter your Smartsheet ID and verify access
2. Upload a screenshot of your table
3. Add context if needed (optional)
4. Review the extracted data
5. Push to Smartsheet with one click

## Limitations

- Works best with simple grid structures
- Does not support merged cells or complex formatting
- Accuracy depends on image quality

## Future Enhancements

- Interactive table preview
- CSV export option
- Support for more complex table structures