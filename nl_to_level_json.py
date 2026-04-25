"""
CS2 Level Design - Natural Language to JSON Converter
=====================================================
Converts natural language descriptions into JSON specifications for the CS2 Level Generator.

Uses a multi-step Chain-of-Thought approach optimized for spatial and tactical reasoning:
1. Intent Parsing - Extract key concepts, gameplay goals, AND EXPLICIT REQUIREMENTS
2. Spatial Planning - Determine positions, sizes, and spatial relationships  
3. Tactical Analysis - Analyze chokepoints, sightlines, balance, and timings
4. JSON Generation - Convert analysis into final JSON format

Key Feature: EXPLICIT REQUIREMENTS PRESERVATION
- Original prompt is included in EVERY step
- Explicit values (map size, dimensions, etc.) are extracted and carried through
- Each step must acknowledge and preserve these requirements
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable
import threading
from dataclasses import dataclass
from enum import Enum

# Configure logging
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"converter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ProcessingStep(Enum):
    INTENT_PARSING = "Step 1: Intent Parsing"
    SPATIAL_PLANNING = "Step 2: Spatial Planning"
    TACTICAL_ANALYSIS = "Step 3: Tactical Analysis"
    JSON_GENERATION = "Step 4: JSON Generation"


@dataclass
class StepResult:
    step: ProcessingStep
    success: bool
    content: str
    raw_response: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# SYSTEM PROMPTS FOR EACH STEP
# ============================================================================

SYSTEM_PROMPT_INTENT = """You are an expert CS2 (Counter-Strike 2) level designer analyzing natural language descriptions to extract design intent.

Your task is to parse the user's description and identify:

## EXPLICIT REQUIREMENTS (CRITICAL - Extract these EXACTLY as specified)
Extract ANY explicit numerical or specific values mentioned:
- Map dimensions (e.g., "64x64", "50 by 50", "64 by 64" etc.) -> list as "Map Size: WxH"
- Specific sizes for areas (small, medium, large, or cell counts)
- Exact positions mentioned
- Number of bombsites
- Number of mid areas  
- Sightline lengths
- Chokepoint widths
- Cover density specifications

## DESIGN ANALYSIS
1. **Map Theme/Setting**: What environment is described? (warehouse, desert, urban, etc.)
2. **Gameplay Goals**: What gameplay experience is desired? (aggressive, tactical, balanced)
3. **Team Balance**: Any specific balance considerations mentioned
4. **Key Areas**: Bombsites, mid areas, spawn locations mentioned
5. **Connectivity Style**: Number of lanes (2-lane, 3-lane, 4-lane), connector preferences
6. **Special Features**: Unique elements like verticality, water, hazards, etc.

CRITICAL: Start your response with a "## EXPLICIT REQUIREMENTS" section listing ALL specific values/numbers from the original prompt. These MUST be preserved through all subsequent steps. If the user specified a map size like "64x64" or "64 by 64", this MUST appear in your explicit requirements.

Output your analysis in a structured format with clear sections.
Be thorough but concise. Focus on extractable game design parameters."""

SYSTEM_PROMPT_SPATIAL = """You are a spatial reasoning expert for CS2 level design. Given the design intent, you must determine precise spatial layout.

==============================================================================
CRITICAL: EXPLICIT REQUIREMENTS ARE NON-NEGOTIABLE
==============================================================================
You will receive EXPLICIT REQUIREMENTS extracted from the original prompt.
These MUST be honored EXACTLY:
- If map size is specified (e.g., 64x64), the final output MUST use that size
- If positions are specified, use those positions
- If sizes are specified, use those sizes
- DO NOT default to 40x40 if another size was specified!
==============================================================================

Use a coordinate system where:
- (0,0) is top-left, (1,1) is bottom-right
- X increases left to right
- Y increases top to bottom

SPATIAL PLANNING RULES for CS2:
1. T Spawn should be opposite CT Spawn (typically bottom-left vs top-right, or variations)
2. Bombsites should be positioned to create interesting attack angles
3. Site A is traditionally "harder to retake" (often closer to T spawn)
4. Site B is traditionally "easier to hold" (often closer to CT spawn)
5. Mid areas should connect major pathways and create rotation options
6. Standard layout distances: spawns at edges (0.1-0.2), sites at 0.2-0.3 from corners

For each area, specify:
- Position as {x: 0.0-1.0, y: 0.0-1.0}
- Size: small (4 cells), medium (6 cells), large (9 cells)
- Shape: square, rectangle, L_shape, T_shape, plus, organic
- Position preference: edge, center, any

IMPORTANT: Begin your response with:
## EXPLICIT REQUIREMENTS TO PRESERVE
[List all explicit requirements from the input that MUST be in the final JSON]

Then provide your spatial plan."""

SYSTEM_PROMPT_TACTICAL = """You are a tactical gameplay analyst for CS2 maps. Given the spatial plan, analyze and refine for competitive balance.

==============================================================================
CRITICAL: EXPLICIT REQUIREMENTS ARE NON-NEGOTIABLE
==============================================================================
You will receive EXPLICIT REQUIREMENTS from the original prompt.
- Do NOT change map dimensions - if 64x64 was specified, it stays 64x64
- Do NOT change explicitly specified values
- Only refine aspects that were NOT explicitly specified
==============================================================================

TACTICAL CONSIDERATIONS:
1. **Timings**: 
   - First contact points (where teams can first meet)
   - Rotation times between sites
   - Rush timings to sites

2. **Chokepoints**:
   - Entry fragger spots
   - AWP angles
   - Smoke/flash denial points

3. **Sightlines**:
   - Max sightline length (6-10 cells is balanced, unless specified otherwise)
   - Cross-angles and trading spots
   - One-way visibility concerns

4. **Cover and Positions**:
   - Post-plant positions
   - Anchor positions
   - Retake angles

5. **Lane Structure**:
   - 2-lane: simpler, faster rotations
   - 3-lane: standard competitive (A-Mid-B)
   - 4-lane: complex, requires more map control

IMPORTANT: Begin your response with:
## EXPLICIT REQUIREMENTS TO PRESERVE
[Restate the explicit requirements - especially MAP SIZE]

Then provide tactical recommendations."""

SYSTEM_PROMPT_JSON = """You are a JSON generator for CS2 level specifications. Convert the design analysis into valid JSON.

==============================================================================
CRITICAL: EXPLICIT REQUIREMENTS OVERRIDE DEFAULTS
==============================================================================
You will receive EXPLICIT REQUIREMENTS from the original prompt.
These MUST be honored EXACTLY in the JSON output:

- MAP SIZE: If specified (e.g., "64x64"), use {"width": 64, "height": 64}
  DO NOT use default 40x40 if a different size was requested!
- Any other explicit values must be used exactly as specified
==============================================================================

The output JSON must follow this EXACT schema:

{
  "map_size": {"width": <USE_EXPLICIT_OR_40>, "height": <USE_EXPLICIT_OR_40>},
  "description": "Brief description of the map",
  "spawn_zones": [
    {
      "team": "T" or "CT",
      "size": "small" | "medium" | "large",
      "location": {"x": 0.0-1.0, "y": 0.0-1.0},
      "position_preference": "edge" | "center" | "any",
      "shape": "square" | "rectangle" | "L_shape" | "T_shape" | "plus" | "organic"
    }
  ],
  "bomb_sites": [
    {
      "id": "A" or "B" (or "C" for 3-site maps),
      "size": "small" | "medium" | "large",
      "location": {"x": 0.0-1.0, "y": 0.0-1.0},
      "shape": "square" | "rectangle" | "L_shape" | "T_shape" | "plus" | "organic"
    }
  ],
  "areas": [
    {
      "type": "mid",
      "size": "small" | "medium" | "large",
      "location": {"x": 0.0-1.0, "y": 0.0-1.0}
    }
  ],
  "connectivity": {
    "style": "2-lane" | "3-lane" | "4-lane",
    "max_chokepoint_width": 1-4 (integer)
  },
  "sightline_control": {
    "enabled": true | false,
    "max_consecutive_open": 4-10 (integer, lower = more breaks)
  },
  "cover_objects": {
    "enabled": true | false,
    "density": "low" | "medium" | "high"
  }
}

IMPORTANT:
- Output ONLY valid JSON, no markdown code blocks, no explanation
- HONOR ALL EXPLICIT REQUIREMENTS - especially map_size!
- Check the EXPLICIT REQUIREMENTS section - if map size is listed there, USE IT
- All coordinates must be between 0.0 and 1.0
- Include at least 2 spawn zones (T and CT)
- Include at least 2 bomb sites (A and B)
- Include at least 1 mid area for 3-lane maps"""

# Store prompts in a dict for easy access
STEP_PROMPTS = {
    ProcessingStep.INTENT_PARSING: SYSTEM_PROMPT_INTENT,
    ProcessingStep.SPATIAL_PLANNING: SYSTEM_PROMPT_SPATIAL,
    ProcessingStep.TACTICAL_ANALYSIS: SYSTEM_PROMPT_TACTICAL,
    ProcessingStep.JSON_GENERATION: SYSTEM_PROMPT_JSON,
}

STEP_DESCRIPTIONS = {
    ProcessingStep.INTENT_PARSING: "Extracts EXPLICIT REQUIREMENTS (map size, etc.) + design goals, themes, and key areas.",
    ProcessingStep.SPATIAL_PLANNING: "Determines positions using explicit requirements. Map size and other specs are preserved.",
    ProcessingStep.TACTICAL_ANALYSIS: "Analyzes balance while preserving all explicit requirements from original prompt.",
    ProcessingStep.JSON_GENERATION: "Generates final JSON. EXPLICIT REQUIREMENTS (like map size) override defaults.",
}


# ============================================================================
# OpenAI API CLIENT
# ============================================================================

class OpenAIClient:
    """Handles communication with OpenAI API."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
        logger.info(f"OpenAI client initialized with model: {model}")
    
    def chat(self, system_prompt: str, user_message: str, 
             temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Send a chat completion request to OpenAI."""
        import urllib.request
        import urllib.error
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        logger.debug(f"API Request - Model: {self.model}, Temp: {temperature}")
        logger.debug(f"System prompt length: {len(system_prompt)} chars")
        logger.debug(f"User message length: {len(user_message)} chars")
        
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))
                content = result['choices'][0]['message']['content']
                logger.debug(f"API Response length: {len(content)} chars")
                return content
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            logger.error(f"HTTP Error {e.code}: {error_body}")
            raise Exception(f"API Error {e.code}: {error_body}")
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise


# ============================================================================
# LEVEL CONVERTER - MULTI-STEP PROCESSING
# ============================================================================

class LevelConverter:
    """Converts natural language to JSON using multi-step Chain-of-Thought."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = OpenAIClient(api_key, model)
        self.step_results: Dict[ProcessingStep, StepResult] = {}
        self.user_messages: Dict[ProcessingStep, str] = {}
        logger.info("LevelConverter initialized")
    
    def process(self, prompt: str, 
                progress_callback: Optional[Callable[[ProcessingStep, str, str], None]] = None) -> Dict[str, Any]:
        """
        Process natural language prompt through all steps.
        
        IMPORTANT: The original prompt is passed to EVERY step to preserve explicit requirements.
        """
        logger.info("=" * 60)
        logger.info("STARTING LEVEL CONVERSION")
        logger.info("=" * 60)
        logger.info(f"Input prompt: {prompt[:200]}...")
        
        self.step_results = {}
        self.user_messages = {}
        context = {"original_prompt": prompt}
        
        # Step 1: Intent Parsing (includes explicit requirements extraction)
        user_msg_1 = f"""Analyze this CS2 map description and extract ALL explicit requirements:

=== ORIGINAL PROMPT (preserve all specific values!) ===
{prompt}
=== END ORIGINAL PROMPT ===

Extract explicit requirements (especially map size like "64x64") and analyze the design intent."""

        self.user_messages[ProcessingStep.INTENT_PARSING] = user_msg_1
        self._notify(progress_callback, ProcessingStep.INTENT_PARSING, "running", user_msg_1)
        intent_result = self._run_step(ProcessingStep.INTENT_PARSING, SYSTEM_PROMPT_INTENT, user_msg_1, 0.3)
        self.step_results[ProcessingStep.INTENT_PARSING] = intent_result
        self._notify(progress_callback, ProcessingStep.INTENT_PARSING, 
                    "complete" if intent_result.success else "failed", user_msg_1)
        if not intent_result.success:
            raise Exception(f"Intent parsing failed: {intent_result.error}")
        context["intent"] = intent_result.content
        
        # Step 2: Spatial Planning
        user_msg_2 = f"""Create a spatial plan for this CS2 map.

=== ORIGINAL PROMPT (contains explicit requirements - DO NOT IGNORE!) ===
{prompt}
=== END ORIGINAL PROMPT ===

=== INTENT ANALYSIS (with extracted requirements) ===
{context['intent']}
=== END INTENT ANALYSIS ===

Create a detailed spatial plan. PRESERVE ALL EXPLICIT REQUIREMENTS from the original prompt!
If the original says "64x64", the map MUST be 64x64, not 40x40."""

        self.user_messages[ProcessingStep.SPATIAL_PLANNING] = user_msg_2
        self._notify(progress_callback, ProcessingStep.SPATIAL_PLANNING, "running", user_msg_2)
        spatial_result = self._run_step(ProcessingStep.SPATIAL_PLANNING, SYSTEM_PROMPT_SPATIAL, user_msg_2, 0.4)
        self.step_results[ProcessingStep.SPATIAL_PLANNING] = spatial_result
        self._notify(progress_callback, ProcessingStep.SPATIAL_PLANNING,
                    "complete" if spatial_result.success else "failed", user_msg_2)
        if not spatial_result.success:
            raise Exception(f"Spatial planning failed: {spatial_result.error}")
        context["spatial"] = spatial_result.content
        
        # Step 3: Tactical Analysis
        user_msg_3 = f"""Analyze this layout for tactical balance.

=== ORIGINAL PROMPT (explicit requirements are NON-NEGOTIABLE!) ===
{prompt}
=== END ORIGINAL PROMPT ===

=== SPATIAL PLAN ===
{context['spatial']}
=== END SPATIAL PLAN ===

Provide tactical analysis. DO NOT change any explicit requirements from the original prompt!"""

        self.user_messages[ProcessingStep.TACTICAL_ANALYSIS] = user_msg_3
        self._notify(progress_callback, ProcessingStep.TACTICAL_ANALYSIS, "running", user_msg_3)
        tactical_result = self._run_step(ProcessingStep.TACTICAL_ANALYSIS, SYSTEM_PROMPT_TACTICAL, user_msg_3, 0.4)
        self.step_results[ProcessingStep.TACTICAL_ANALYSIS] = tactical_result
        self._notify(progress_callback, ProcessingStep.TACTICAL_ANALYSIS,
                    "complete" if tactical_result.success else "failed", user_msg_3)
        if not tactical_result.success:
            raise Exception(f"Tactical analysis failed: {tactical_result.error}")
        context["tactical"] = tactical_result.content
        
        # Step 4: JSON Generation
        user_msg_4 = f"""Generate the final JSON specification.

=== ORIGINAL PROMPT (CHECK FOR MAP SIZE AND OTHER EXPLICIT VALUES!) ===
{prompt}
=== END ORIGINAL PROMPT ===

=== INTENT ANALYSIS (has EXPLICIT REQUIREMENTS section) ===
{context['intent']}
=== END INTENT ANALYSIS ===

=== SPATIAL PLAN ===
{context['spatial']}
=== END SPATIAL PLAN ===

=== TACTICAL ANALYSIS ===
{context['tactical']}
=== END TACTICAL ANALYSIS ===

Generate valid JSON. 
CRITICAL: If the original prompt specified a map size (like 64x64), use THAT size, not 40x40!
Output ONLY the JSON, no markdown, no explanation."""

        self.user_messages[ProcessingStep.JSON_GENERATION] = user_msg_4
        self._notify(progress_callback, ProcessingStep.JSON_GENERATION, "running", user_msg_4)
        json_result = self._run_step(ProcessingStep.JSON_GENERATION, SYSTEM_PROMPT_JSON, user_msg_4, 0.2, 3000)
        self.step_results[ProcessingStep.JSON_GENERATION] = json_result
        self._notify(progress_callback, ProcessingStep.JSON_GENERATION,
                    "complete" if json_result.success else "failed", user_msg_4)
        if not json_result.success:
            raise Exception(f"JSON generation failed: {json_result.error}")
        
        # Parse and validate final JSON
        try:
            final_json = self._extract_json(json_result.content)
            self._validate_json(final_json)
            logger.info("Level conversion completed successfully")
            logger.info(f"Final map size: {final_json.get('map_size', {})}")
            return final_json
        except Exception as e:
            logger.error(f"JSON validation failed: {e}")
            raise Exception(f"JSON validation failed: {e}")
    
    def _run_step(self, step: ProcessingStep, system_prompt: str, user_message: str,
                  temperature: float, max_tokens: int = 2000) -> StepResult:
        """Run a single processing step."""
        try:
            response = self.client.chat(system_prompt, user_message, temperature, max_tokens)
            return StepResult(
                step=step,
                success=True,
                content=response,
                raw_response=response
            )
        except Exception as e:
            return StepResult(
                step=step,
                success=False,
                content="",
                error=str(e)
            )
    
    def _notify(self, callback, step: ProcessingStep, status: str, user_message: str):
        """Send progress notification."""
        logger.info(f"{step.value}: {status}")
        if callback:
            callback(step, status, user_message)
    
    def _extract_json(self, content: str) -> Dict:
        """Extract JSON from response, handling markdown code blocks."""
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        
        return json.loads(content)
    
    def _validate_json(self, data: Dict) -> bool:
        """Validate the JSON structure meets minimum requirements."""
        required_keys = ["spawn_zones", "bomb_sites"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing required key: {key}")
        
        spawns = data.get("spawn_zones", [])
        teams = [s.get("team") for s in spawns]
        if "T" not in teams or "CT" not in teams:
            raise ValueError("Must have both T and CT spawn zones")
        
        sites = data.get("bomb_sites", [])
        if len(sites) < 2:
            raise ValueError("Must have at least 2 bomb sites")
        
        for zone in spawns + sites:
            loc = zone.get("location", {})
            x, y = loc.get("x", 0.5), loc.get("y", 0.5)
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError(f"Coordinates out of range: ({x}, {y})")
        
        return True


# ============================================================================
# GUI APPLICATION
# ============================================================================

class ConverterGUI:
    """Main GUI application for the NL to JSON converter."""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CS2 Level Designer - Natural Language to JSON")
        self.root.geometry("1500x950")
        self.root.configure(bg="#1a1a2e")
        
        self.api_key = tk.StringVar()
        self.remember_api_key = tk.BooleanVar(value=True)
        self.model = tk.StringVar(value="gpt-4o")
        self.output_path = tk.StringVar(
            value=r"D:\_School\BUAS\Level builders\CS2\JSON to VMAP\JSON prompt results"
        )
        self.is_processing = False
        self.converter: Optional[LevelConverter] = None
        
        self._setup_styles()
        self._create_widgets()
        self._load_settings()
        
        logger.info("GUI initialized")
    
    def _setup_styles(self):
        """Configure ttk styles for dark theme."""
        style = ttk.Style()
        style.theme_use('clam')
        
        self.colors = {
            'bg': '#1a1a2e',
            'bg_light': '#16213e',
            'bg_panel': '#0f3460',
            'accent': '#e94560',
            'accent_hover': '#ff6b6b',
            'text': '#eaeaea',
            'text_dim': '#a0a0a0',
            'success': '#4ecdc4',
            'warning': '#ffd93d',
            'error': '#ff6b6b',
            'step1': '#ff6b6b',
            'step2': '#4ecdc4', 
            'step3': '#ffd93d',
            'step4': '#a78bfa'
        }
        
        style.configure('Dark.TFrame', background=self.colors['bg'])
        style.configure('Panel.TFrame', background=self.colors['bg_panel'])
        style.configure('Dark.TLabel', background=self.colors['bg'], foreground=self.colors['text'])
        style.configure('Panel.TLabel', background=self.colors['bg_panel'], foreground=self.colors['text'])
        style.configure('Title.TLabel', background=self.colors['bg'], foreground=self.colors['text'], 
                       font=('Segoe UI', 18, 'bold'))
        style.configure('Subtitle.TLabel', background=self.colors['bg'], foreground=self.colors['text_dim'],
                       font=('Segoe UI', 10))
        
        style.configure('TEntry', fieldbackground=self.colors['bg_light'], foreground=self.colors['text'])
        style.configure('TCombobox', fieldbackground=self.colors['bg_light'], foreground=self.colors['text'])
        
        style.configure('Dark.TNotebook', background=self.colors['bg_panel'])
        style.configure('Dark.TNotebook.Tab', background=self.colors['bg_light'], 
                       foreground=self.colors['text'], padding=(15, 8),
                       font=('Segoe UI', 10, 'bold'))
        style.map('Dark.TNotebook.Tab', 
                 background=[('selected', self.colors['bg_panel'])],
                 foreground=[('selected', self.colors['text'])])
    
    def _create_widgets(self):
        """Create all GUI widgets."""
        main_frame = ttk.Frame(self.root, style='Dark.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        self._create_header(main_frame)
        
        content = ttk.Frame(main_frame, style='Dark.TFrame')
        content.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=2)
        content.columnconfigure(2, weight=1)
        
        self._create_input_panel(content)
        self._create_steps_panel(content)
        self._create_output_panel(content)
        self._create_settings_panel(main_frame)
    
    def _create_header(self, parent):
        """Create header section."""
        header = ttk.Frame(parent, style='Dark.TFrame')
        header.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header, text="🎮 CS2 Level Designer", style='Title.TLabel').pack(side=tk.LEFT)
        ttk.Label(header, text="Natural Language → JSON (with Explicit Requirements Preservation)", 
                 style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(15, 0), pady=(8, 0))
        
        api_frame = ttk.Frame(header, style='Dark.TFrame')
        api_frame.pack(side=tk.RIGHT)
        
        remember_cb = tk.Checkbutton(api_frame, text="Remember", variable=self.remember_api_key,
                                     bg=self.colors['bg'], fg=self.colors['text'],
                                     selectcolor=self.colors['bg_light'], activebackground=self.colors['bg'],
                                     activeforeground=self.colors['text'], font=('Segoe UI', 9))
        remember_cb.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(api_frame, text="OpenAI API Key:", style='Dark.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        api_entry = ttk.Entry(api_frame, textvariable=self.api_key, width=40, show="•")
        api_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(api_frame, text="Model:", style='Dark.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        model_combo = ttk.Combobox(api_frame, textvariable=self.model, width=15,
                                   values=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"])
        model_combo.pack(side=tk.LEFT)
    
    def _create_input_panel(self, parent):
        """Create input panel with prompt editor."""
        frame = tk.Frame(parent, bg=self.colors['bg_panel'], relief='flat', bd=0)
        frame.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        
        title_frame = tk.Frame(frame, bg=self.colors['bg_panel'])
        title_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        tk.Label(title_frame, text="📝 PROMPT INPUT", font=('Segoe UI', 12, 'bold'),
                bg=self.colors['bg_panel'], fg=self.colors['text']).pack(side=tk.LEFT)
        
        btn_frame = tk.Frame(title_frame, bg=self.colors['bg_panel'])
        btn_frame.pack(side=tk.RIGHT)
        
        tk.Button(btn_frame, text="📂 Load", command=self.load_prompt,
                 bg=self.colors['bg_light'], fg=self.colors['text'], relief='flat',
                 font=('Segoe UI', 9), padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="💾 Save", command=self.save_prompt,
                 bg=self.colors['bg_light'], fg=self.colors['text'], relief='flat',
                 font=('Segoe UI', 9), padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="📋 Example", command=self.load_example,
                 bg=self.colors['bg_light'], fg=self.colors['text'], relief='flat',
                 font=('Segoe UI', 9), padx=10).pack(side=tk.LEFT, padx=2)
        
        # Hint about explicit requirements
        hint_frame = tk.Frame(frame, bg=self.colors['warning'])
        hint_frame.pack(fill=tk.X, padx=15, pady=(0, 5))
        tk.Label(hint_frame, text="💡 Tip: Explicit values (e.g., '64x64 map') are preserved through all steps!",
                font=('Segoe UI', 8), bg=self.colors['warning'], fg='black').pack(padx=5, pady=3)
        
        self.prompt_text = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=('Consolas', 10),
            bg=self.colors['bg_light'], fg=self.colors['text'],
            insertbackground=self.colors['text'], relief='flat',
            padx=10, pady=10
        )
        self.prompt_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        self.generate_btn = tk.Button(
            frame, text="🚀 GENERATE JSON", command=self.generate,
            bg=self.colors['accent'], fg='white', font=('Segoe UI', 12, 'bold'),
            relief='flat', padx=30, pady=12, cursor='hand2'
        )
        self.generate_btn.pack(pady=(0, 15))
        self.generate_btn.bind('<Enter>', lambda e: self.generate_btn.configure(bg=self.colors['accent_hover']))
        self.generate_btn.bind('<Leave>', lambda e: self.generate_btn.configure(bg=self.colors['accent']))
    
    def _create_steps_panel(self, parent):
        """Create tabbed panel showing intermediate steps."""
        frame = tk.Frame(parent, bg=self.colors['bg_panel'], relief='flat', bd=0)
        frame.grid(row=0, column=1, sticky='nsew', padx=5)
        
        title_frame = tk.Frame(frame, bg=self.colors['bg_panel'])
        title_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        tk.Label(title_frame, text="🔄 PROCESSING STEPS", font=('Segoe UI', 12, 'bold'),
                bg=self.colors['bg_panel'], fg=self.colors['text']).pack(side=tk.LEFT)
        
        self.status_indicators = {}
        status_frame = tk.Frame(title_frame, bg=self.colors['bg_panel'])
        status_frame.pack(side=tk.RIGHT)
        
        step_colors = {
            ProcessingStep.INTENT_PARSING: self.colors['step1'],
            ProcessingStep.SPATIAL_PLANNING: self.colors['step2'],
            ProcessingStep.TACTICAL_ANALYSIS: self.colors['step3'],
            ProcessingStep.JSON_GENERATION: self.colors['step4'],
        }
        
        for i, step in enumerate(ProcessingStep):
            indicator = tk.Label(status_frame, text="●", font=('Segoe UI', 14),
                               bg=self.colors['bg_panel'], fg=self.colors['text_dim'])
            indicator.pack(side=tk.LEFT, padx=3)
            self.status_indicators[step] = (indicator, step_colors[step])
        
        self.notebook = ttk.Notebook(frame, style='Dark.TNotebook')
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        self.step_tabs = {}
        self.step_system_texts = {}
        self.step_user_texts = {}
        self.step_response_texts = {}
        
        tab_names = {
            ProcessingStep.INTENT_PARSING: "1️⃣ Intent",
            ProcessingStep.SPATIAL_PLANNING: "2️⃣ Spatial",
            ProcessingStep.TACTICAL_ANALYSIS: "3️⃣ Tactical",
            ProcessingStep.JSON_GENERATION: "4️⃣ JSON",
        }
        
        for step in ProcessingStep:
            tab = tk.Frame(self.notebook, bg=self.colors['bg_light'])
            self.notebook.add(tab, text=tab_names[step])
            self.step_tabs[step] = tab
            
            desc_frame = tk.Frame(tab, bg=step_colors[step])
            desc_frame.pack(fill=tk.X)
            tk.Label(desc_frame, text=STEP_DESCRIPTIONS[step], font=('Segoe UI', 9),
                    bg=step_colors[step], fg='white', wraplength=500).pack(padx=10, pady=8)
            
            paned = ttk.PanedWindow(tab, orient=tk.VERTICAL)
            paned.pack(fill=tk.BOTH, expand=True, pady=5)
            
            system_frame = tk.LabelFrame(tab, text="📋 SYSTEM PROMPT", 
                                        bg=self.colors['bg_light'], fg=self.colors['text'],
                                        font=('Segoe UI', 9, 'bold'))
            paned.add(system_frame, weight=1)
            
            system_text = scrolledtext.ScrolledText(
                system_frame, wrap=tk.WORD, font=('Consolas', 9),
                bg=self.colors['bg'], fg=self.colors['text_dim'],
                height=8, relief='flat', padx=8, pady=8
            )
            system_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            system_text.insert('1.0', STEP_PROMPTS[step])
            system_text.config(state=tk.DISABLED)
            self.step_system_texts[step] = system_text
            
            user_frame = tk.LabelFrame(tab, text="💬 USER MESSAGE (includes original prompt!)", 
                                      bg=self.colors['bg_light'], fg=self.colors['text'],
                                      font=('Segoe UI', 9, 'bold'))
            paned.add(user_frame, weight=1)
            
            user_text = scrolledtext.ScrolledText(
                user_frame, wrap=tk.WORD, font=('Consolas', 9),
                bg=self.colors['bg'], fg=self.colors['warning'],
                height=8, relief='flat', padx=8, pady=8
            )
            user_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            user_text.config(state=tk.DISABLED)
            self.step_user_texts[step] = user_text
            
            response_frame = tk.LabelFrame(tab, text="🤖 LLM RESPONSE", 
                                          bg=self.colors['bg_light'], fg=self.colors['text'],
                                          font=('Segoe UI', 9, 'bold'))
            paned.add(response_frame, weight=2)
            
            response_text = scrolledtext.ScrolledText(
                response_frame, wrap=tk.WORD, font=('Consolas', 9),
                bg=self.colors['bg'], fg=self.colors['success'],
                height=12, relief='flat', padx=8, pady=8
            )
            response_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            response_text.config(state=tk.DISABLED)
            self.step_response_texts[step] = response_text
    
    def _create_output_panel(self, parent):
        """Create output panel with JSON result."""
        frame = tk.Frame(parent, bg=self.colors['bg_panel'], relief='flat', bd=0)
        frame.grid(row=0, column=2, sticky='nsew', padx=(10, 0))
        
        title_frame = tk.Frame(frame, bg=self.colors['bg_panel'])
        title_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        tk.Label(title_frame, text="📄 JSON OUTPUT", font=('Segoe UI', 12, 'bold'),
                bg=self.colors['bg_panel'], fg=self.colors['text']).pack(side=tk.LEFT)
        
        btn_frame = tk.Frame(title_frame, bg=self.colors['bg_panel'])
        btn_frame.pack(side=tk.RIGHT)
        
        tk.Button(btn_frame, text="📋 Copy", command=self.copy_output,
                 bg=self.colors['bg_light'], fg=self.colors['text'], relief='flat',
                 font=('Segoe UI', 9), padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="💾 Save", command=self.save_output,
                 bg=self.colors['success'], fg='white', relief='flat',
                 font=('Segoe UI', 9, 'bold'), padx=10).pack(side=tk.LEFT, padx=2)
        
        self.output_text = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=('Consolas', 10),
            bg=self.colors['bg_light'], fg=self.colors['text'],
            insertbackground=self.colors['text'], relief='flat',
            padx=10, pady=10
        )
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
    
    def _create_settings_panel(self, parent):
        """Create settings and status panel."""
        frame = tk.Frame(parent, bg=self.colors['bg_light'], relief='flat')
        frame.pack(fill=tk.X, pady=(20, 0))
        
        path_frame = tk.Frame(frame, bg=self.colors['bg_light'])
        path_frame.pack(fill=tk.X, padx=15, pady=10)
        
        tk.Label(path_frame, text="Output Folder:", font=('Segoe UI', 10),
                bg=self.colors['bg_light'], fg=self.colors['text']).pack(side=tk.LEFT)
        
        path_entry = tk.Entry(path_frame, textvariable=self.output_path, width=70,
                             font=('Consolas', 9), bg=self.colors['bg'], fg=self.colors['text'],
                             relief='flat')
        path_entry.pack(side=tk.LEFT, padx=(10, 5), ipady=5)
        
        tk.Button(path_frame, text="Browse...", command=self.browse_output,
                 bg=self.colors['bg_panel'], fg=self.colors['text'], relief='flat',
                 font=('Segoe UI', 9), padx=10).pack(side=tk.LEFT)
        
        self.status_var = tk.StringVar(value="Ready - Enter your map description and click Generate")
        self.status_label = tk.Label(frame, textvariable=self.status_var, font=('Segoe UI', 10),
                                    bg=self.colors['bg_light'], fg=self.colors['text_dim'])
        self.status_label.pack(pady=(0, 10))
        
        self.progress = ttk.Progressbar(frame, mode='indeterminate', length=400)
        self.progress.pack(pady=(0, 15))
    
    # ========================================================================
    # ACTIONS
    # ========================================================================
    
    def load_prompt(self):
        """Load prompt from text file."""
        filepath = filedialog.askopenfilename(
            title="Load Prompt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.prompt_text.delete('1.0', tk.END)
                self.prompt_text.insert('1.0', content)
                self.status_var.set(f"Loaded: {os.path.basename(filepath)}")
                logger.info(f"Loaded prompt from: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {e}")
                logger.error(f"Failed to load prompt: {e}")
    
    def save_prompt(self):
        """Save prompt to text file."""
        filepath = filedialog.asksaveasfilename(
            title="Save Prompt",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(self.prompt_text.get('1.0', tk.END))
                self.status_var.set(f"Saved: {os.path.basename(filepath)}")
                logger.info(f"Saved prompt to: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")
                logger.error(f"Failed to save prompt: {e}")
    
    def load_example(self):
        """Load an example prompt with explicit requirements."""
        example = """Design a competitive CS2 defusal map with a 64x64 grid size.

The map is set in an abandoned industrial warehouse complex.

Layout requirements:
- Classic 3-lane layout
- T spawn in the southwest corner (around x:0.1, y:0.9)
- CT spawn in the northeast (around x:0.9, y:0.1)
- Bombsite A: northwest, large size, open warehouse floor
- Bombsite B: southeast, medium size, loading dock area

Mid area should be central with a catwalk design.

Tactical settings:
- Sightlines no longer than 10 cells (max_consecutive_open: 10)
- Chokepoint width: 2 cells
- Cover density: medium

The map should favor tactical play with smoke/flash opportunities."""
        
        self.prompt_text.delete('1.0', tk.END)
        self.prompt_text.insert('1.0', example)
        self.status_var.set("Example prompt loaded (note: 64x64 map size specified)")
        logger.info("Loaded example prompt")
    
    def copy_output(self):
        """Copy output JSON to clipboard."""
        content = self.output_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.status_var.set("JSON copied to clipboard!")
            logger.info("Output copied to clipboard")
    
    def save_output(self):
        """Save output JSON to file."""
        content = self.output_text.get('1.0', tk.END).strip()
        if not content:
            messagebox.showwarning("Warning", "No output to save!")
            return
        
        output_dir = self.output_path.get()
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"level_prompt_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            self.status_var.set(f"✓ Saved: {filename}")
            logger.info(f"Output saved to: {filepath}")
            messagebox.showinfo("Success", f"Saved to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
            logger.error(f"Failed to save output: {e}")
    
    def browse_output(self):
        """Browse for output directory."""
        folder = filedialog.askdirectory(
            title="Select Output Folder",
            initialdir=self.output_path.get()
        )
        if folder:
            self.output_path.set(folder)
            logger.info(f"Output path set to: {folder}")
    
    def generate(self):
        """Start the generation process."""
        if self.is_processing:
            return
        
        api_key = self.api_key.get().strip()
        if not api_key:
            messagebox.showerror("Error", "Please enter your OpenAI API key!")
            return
        
        prompt = self.prompt_text.get('1.0', tk.END).strip()
        if not prompt:
            messagebox.showerror("Error", "Please enter a map description!")
            return
        
        self.output_text.delete('1.0', tk.END)
        for step in ProcessingStep:
            user_text = self.step_user_texts[step]
            user_text.config(state=tk.NORMAL)
            user_text.delete('1.0', tk.END)
            user_text.insert('1.0', "Waiting...")
            user_text.config(state=tk.DISABLED)
            
            response_text = self.step_response_texts[step]
            response_text.config(state=tk.NORMAL)
            response_text.delete('1.0', tk.END)
            response_text.insert('1.0', "Waiting for processing...")
            response_text.config(state=tk.DISABLED)
            
            indicator, _ = self.status_indicators[step]
            indicator.config(fg=self.colors['text_dim'])
        
        self.is_processing = True
        self.generate_btn.config(state=tk.DISABLED, text="⏳ Processing...")
        self.progress.start(10)
        
        thread = threading.Thread(target=self._process_thread, args=(api_key, prompt))
        thread.daemon = True
        thread.start()
    
    def _process_thread(self, api_key: str, prompt: str):
        """Background thread for processing."""
        try:
            self.converter = LevelConverter(api_key, self.model.get())
            result = self.converter.process(prompt, self._on_step_progress)
            self.root.after(0, lambda: self._on_complete(result))
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            self.root.after(0, lambda: self._on_error(str(e)))
    
    def _on_step_progress(self, step: ProcessingStep, status: str, user_message: str):
        """Callback for step progress updates."""
        def update():
            indicator, color = self.status_indicators[step]
            
            if status == "running":
                indicator.config(fg=self.colors['warning'])
                user_text = self.step_user_texts[step]
                user_text.config(state=tk.NORMAL)
                user_text.delete('1.0', tk.END)
                user_text.insert('1.0', user_message)
                user_text.config(state=tk.DISABLED)
                
                response_text = self.step_response_texts[step]
                response_text.config(state=tk.NORMAL)
                response_text.delete('1.0', tk.END)
                response_text.insert('1.0', "🔄 Processing...")
                response_text.config(state=tk.DISABLED)
                
                tab_index = list(ProcessingStep).index(step)
                self.notebook.select(tab_index)
                
            elif status == "complete":
                indicator.config(fg=color)
                if self.converter and step in self.converter.step_results:
                    result = self.converter.step_results[step]
                    response_text = self.step_response_texts[step]
                    response_text.config(state=tk.NORMAL)
                    response_text.delete('1.0', tk.END)
                    response_text.insert('1.0', result.content if result.success else f"ERROR: {result.error}")
                    response_text.config(state=tk.DISABLED)
                    
            elif status == "failed":
                indicator.config(fg=self.colors['error'])
                if self.converter and step in self.converter.step_results:
                    result = self.converter.step_results[step]
                    response_text = self.step_response_texts[step]
                    response_text.config(state=tk.NORMAL)
                    response_text.delete('1.0', tk.END)
                    response_text.insert('1.0', f"❌ ERROR: {result.error}")
                    response_text.config(state=tk.DISABLED)
            
            self.status_var.set(f"{step.value}: {status}")
        
        self.root.after(0, update)
    
    def _on_complete(self, result: Dict):
        """Handle successful completion."""
        self.is_processing = False
        self.generate_btn.config(state=tk.NORMAL, text="🚀 GENERATE JSON")
        self.progress.stop()
        
        json_str = json.dumps(result, indent=2)
        self.output_text.delete('1.0', tk.END)
        self.output_text.insert('1.0', json_str)
        
        # Show map size in status
        map_size = result.get('map_size', {})
        self.status_var.set(f"✓ Complete! Map size: {map_size.get('width', '?')}x{map_size.get('height', '?')}")
        logger.info("Generation completed successfully")
    
    def _on_error(self, error: str):
        """Handle generation error."""
        self.is_processing = False
        self.generate_btn.config(state=tk.NORMAL, text="🚀 GENERATE JSON")
        self.progress.stop()
        
        self.status_var.set(f"✗ Error: {error}")
        messagebox.showerror("Generation Error", f"Failed to generate:\n\n{error}")
        logger.error(f"Generation error displayed: {error}")
    
    def _load_settings(self):
        """Load saved settings."""
        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    if settings.get('remember_api_key', True):
                        self.api_key.set(settings.get('api_key', ''))
                    self.remember_api_key.set(settings.get('remember_api_key', True))
                    self.model.set(settings.get('model', 'gpt-4o'))
                    self.output_path.set(settings.get('output_path', self.output_path.get()))
                logger.info("Settings loaded")
            except Exception as e:
                logger.warning(f"Failed to load settings: {e}")
    
    def _save_settings(self):
        """Save settings on close."""
        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
        try:
            settings = {
                'api_key': self.api_key.get() if self.remember_api_key.get() else '',
                'remember_api_key': self.remember_api_key.get(),
                'model': self.model.get(),
                'output_path': self.output_path.get()
            }
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            logger.info("Settings saved")
        except Exception as e:
            logger.warning(f"Failed to save settings: {e}")
    
    def run(self):
        """Run the application."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
    
    def _on_close(self):
        """Handle window close."""
        self._save_settings()
        self.root.destroy()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("CS2 LEVEL DESIGNER - NL TO JSON CONVERTER v2")
    logger.info("With Explicit Requirements Preservation")
    logger.info("=" * 60)
    
    root = tk.Tk()
    app = ConverterGUI(root)
    app.run()


if __name__ == "__main__":
    main()