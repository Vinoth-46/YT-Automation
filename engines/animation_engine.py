import os
import re
import math
import shutil
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class AnimationEngine:
    def __init__(self):
        # Locate standard fonts
        self.fonts_dir = os.path.join(os.getcwd(), "assets", "fonts")
        self.tamil_font_path = os.path.join(self.fonts_dir, "NotoSansTamil-Bold.ttf")
        self.latin_font_path = os.path.join(self.fonts_dir, "NotoSans-Bold.ttf")

    def _get_font(self, size, prefer_tamil=False):
        """Load the correct font with fallbacks."""
        font_path = self.tamil_font_path if prefer_tamil else self.latin_font_path
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception as e:
                logger.warning(f"Failed to load truetype font {font_path}: {e}")
        
        # System font fallbacks
        fallbacks = ["arial.ttf", "msyh.ttc", "Helvetica", "sans-serif"]
        for f in fallbacks:
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _select_font(self, text, size):
        """Auto-select font based on text content.
        
        Uses Tamil font only if text contains Tamil characters (U+0B80..U+0BFF).
        Otherwise uses Latin font (NotoSans-Bold) to avoid □ square rendering.
        """
        has_tamil = bool(re.search(r'[\u0B80-\u0BFF]', text))
        return self._get_font(size, prefer_tamil=has_tamil)

    def render_animation(self, anim_config, duration, output_dir):
        """Generates a sequence of PNG frames for a scene's animation config.
        
        Args:
            anim_config: dict containing 'type', 'title', and 'details'
            duration: float, duration of the scene in seconds
            output_dir: str, path to temp folder where PNGs should be written
            
        Returns:
            str: path pattern suitable for FFmpeg (e.g. 'output_dir/frame_%04d.png')
        """
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        
        fps = 30
        total_frames = int(duration * fps)
        
        anim_type = anim_config.get("type", "").lower()
        title = anim_config.get("title", "INFO")
        details = anim_config.get("details", {})
        
        logger.info(f"Rendering {total_frames} frames of '{anim_type}' animation in '{output_dir}'")
        
        for frame_idx in range(total_frames):
            # Create a transparent base canvas (1080x1920)
            img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # 1. Animate card container appearance (Frames 0 to 15)
            # Safe zone: X from 60 to 1020 (width 960), Y from 350 to 1250 (height 900)
            card_x1, card_y1 = 60, 350
            card_x2, card_y2 = 1020, 1250
            
            # Linear interpolation factor for card entry
            t_card = min(frame_idx / 15.0, 1.0)
            
            # Fade in card opacity: max 210/255 (82% opacity)
            card_alpha = int(210 * t_card)
            border_alpha = int(60 * t_card)
            
            if card_alpha > 0:
                # Glassmorphic Card Background
                draw.rounded_rectangle(
                    [card_x1, card_y1, card_x2, card_y2],
                    radius=30,
                    fill=(18, 18, 18, card_alpha),
                    outline=(255, 255, 255, border_alpha),
                    width=3
                )
                
                # Card Title Text (Fades in slightly after card starts appearing)
                t_text = min(max((frame_idx - 5) / 10.0, 0.0), 1.0)
                text_alpha = int(255 * t_text)
                
                if text_alpha > 0:
                    title_font = self._select_font(title, 44)
                    # Draw title centered
                    bbox = draw.textbbox((0, 0), title.upper(), font=title_font)
                    title_w = bbox[2] - bbox[0]
                    title_x = 540 - (title_w // 2)
                    title_y = card_y1 + 40
                    
                    # Draw subtle shadow for text
                    draw.text((title_x + 2, title_y + 2), title.upper(), font=title_font, fill=(0, 0, 0, int(180 * t_text)))
                    # Draw yellow glowing title text
                    draw.text((title_x, title_y), title.upper(), font=title_font, fill=(255, 215, 0, text_alpha))
                    
                    # Draw a thin horizontal glowing line under the title
                    line_w = int(250 * t_text)
                    draw.line(
                        [540 - line_w, title_y + 65, 540 + line_w, title_y + 65],
                        fill=(0, 229, 255, int(150 * t_text)),
                        width=2
                    )
            
            # 2. Render Template Contents (Frames 15 onwards)
            if frame_idx >= 15:
                t_content = min((frame_idx - 15) / 15.0, 1.0) # generic content fade-in
                content_alpha = int(255 * t_content)
                
                if anim_type == "comparison":
                    self._draw_comparison(draw, frame_idx - 15, details, content_alpha)
                elif anim_type == "ratio":
                    self._draw_ratio(draw, frame_idx - 15, details, content_alpha)
                elif anim_type == "structural":
                    self._draw_structural(draw, frame_idx - 15, details, content_alpha)
                elif anim_type == "progress":
                    self._draw_progress(draw, frame_idx - 15, details, content_alpha)
                elif anim_type == "warning":
                    self._draw_warning(draw, frame_idx - 15, details, content_alpha)
                else:
                    # Default: just display details in a simple list
                    self._draw_default(draw, frame_idx - 15, title, details, content_alpha)
                    
            # Save frame to output directory
            frame_path = os.path.join(output_dir, f"frame_{frame_idx:04d}.png")
            img.save(frame_path, "PNG")
            
        return os.path.join(output_dir, "frame_%04d.png")

    def _draw_comparison(self, draw, f, details, alpha):
        """Render two columns comparing properties of two items."""
        item_a = details.get("item_a", "Item A")
        item_b = details.get("item_b", "Item B")
        points_a = details.get("points_a", [])
        points_b = details.get("points_b", [])
        
        col_y = 480
        left_center = 310
        right_center = 770
        
        # 1. Draw Column Header Text
        header_font = self._select_font(item_a + item_b, 38)
        
        # Item A Header (e.g. M-Sand)
        bbox_a = draw.textbbox((0, 0), item_a, font=header_font)
        draw.text((left_center - (bbox_a[2] - bbox_a[0])//2, col_y), item_a, font=header_font, fill=(255, 255, 255, alpha))
        
        # Item B Header (e.g. River Sand)
        bbox_b = draw.textbbox((0, 0), item_b, font=header_font)
        draw.text((right_center - (bbox_b[2] - bbox_b[0])//2, col_y), item_b, font=header_font, fill=(255, 255, 255, alpha))
        
        # Divider Line between columns (grows vertically)
        t_div = min(f / 20.0, 1.0)
        div_h = int(600 * t_div)
        draw.line([540, col_y + 60, 540, col_y + 60 + div_h], fill=(255, 255, 255, int(40 * t_div)), width=2)
        
        # 2. Draw Column Illustrations (Grains or blocks drawing themselves)
        illust_y = col_y + 120
        t_illust = min(max((f - 10) / 25.0, 0.0), 1.0)
        illust_alpha = int(255 * t_illust)
        
        if illust_alpha > 0:
            # Draw Item A graphic (Left)
            if "sand" in item_a.lower() or "sand" in details.get("title", "").lower() or "m-sand" in item_a.lower():
                # Draw M-Sand (angular/sharp grey triangles)
                for seed, offset in enumerate([(-40, 20), (-20, 0), (0, 15), (20, -5), (40, 25), (-30, -10), (30, 5)]):
                    cx, cy = left_center + offset[0], illust_y + offset[1]
                    draw.polygon(
                        [(cx-15, cy+15), (cx, cy-15), (cx+15, cy+10), (cx-5, cy+20)],
                        fill=(120, 125, 130, int(150 * t_illust)),
                        outline=(200, 205, 210, illust_alpha),
                    )
            elif "brick" in item_a.lower() or "red" in item_a.lower():
                # Draw Red Brick (solid rectangle)
                draw.rectangle(
                    [left_center - 60, illust_y - 25, left_center + 60, illust_y + 25],
                    fill=(180, 50, 40, int(160 * t_illust)),
                    outline=(255, 100, 90, illust_alpha),
                    width=3
                )
            else:
                # Default clean icon box (Yellow)
                draw.rectangle(
                    [left_center - 30, illust_y - 30, left_center + 30, illust_y + 30],
                    fill=(255, 215, 0, int(40 * t_illust)),
                    outline=(255, 215, 0, illust_alpha),
                    width=2
                )
                
            # Draw Item B graphic (Right)
            if "sand" in item_b.lower() or "sand" in details.get("title", "").lower() or "river" in item_b.lower():
                # Draw River Sand (rounded smooth yellow circles)
                for seed, offset in enumerate([(-45, 15), (-15, 25), (10, 10), (35, 20), (-25, 0), (25, -5), (0, -15)]):
                    cx, cy = right_center + offset[0], illust_y + offset[1]
                    draw.ellipse(
                        [cx-15, cy-15, cx+15, cy+15],
                        fill=(220, 180, 80, int(150 * t_illust)),
                        outline=(255, 220, 120, illust_alpha),
                    )
            elif "block" in item_b.lower() or "solid" in item_b.lower() or "hollow" in item_b.lower():
                # Draw Grey Block (rectangle with hollow openings)
                draw.rectangle(
                    [right_center - 70, illust_y - 30, right_center + 70, illust_y + 30],
                    fill=(90, 95, 100, int(160 * t_illust)),
                    outline=(180, 185, 190, illust_alpha),
                    width=3
                )
                # Hollow spaces
                draw.rectangle([right_center - 45, illust_y - 15, right_center - 10, illust_y + 15], fill=(18, 18, 18, int(200 * t_illust)))
                draw.rectangle([right_center + 10, illust_y - 15, right_center + 45, illust_y + 15], fill=(18, 18, 18, int(200 * t_illust)))
            else:
                # Default clean icon circle (Cyan)
                draw.ellipse(
                    [right_center - 30, illust_y - 30, right_center + 30, illust_y + 30],
                    fill=(0, 229, 255, int(40 * t_illust)),
                    outline=(0, 229, 255, illust_alpha),
                    width=2
                )

        # 3. Draw Checklist Points (Staggered slide-in from frames 35+)
        pt_font = self._select_font(' '.join(points_a + points_b), 28)
        pt_start_y = col_y + 240
        max_pts = max(len(points_a), len(points_b))
        
        for idx in range(max_pts):
            t_pt = min(max((f - 30 - idx * 15) / 15.0, 0.0), 1.0)
            pt_alpha = int(255 * t_pt)
            
            if pt_alpha > 0:
                y = pt_start_y + idx * 95
                
                # Slide-in offset
                slide_offset = int((1.0 - t_pt) * -30)
                
                # Left Point
                if idx < len(points_a):
                    text_a = points_a[idx]
                    # Icon: check mark (green) or cross (red)
                    is_good = not any(w in text_a.lower() for w in ["silt", "high cost", "impurities", "illegal", "weak", "bad", "mistake", "contain", "cracks"])
                    icon = "✔" if is_good else "✖"
                    icon_color = (0, 230, 118, pt_alpha) if is_good else (255, 61, 0, pt_alpha)
                    
                    draw.text((left_center - 130 + slide_offset, y), icon, font=pt_font, fill=icon_color)
                    draw.text((left_center - 95 + slide_offset, y), text_a, font=pt_font, fill=(230, 230, 230, pt_alpha))
                    
                # Right Point
                if idx < len(points_b):
                    text_b = points_b[idx]
                    is_good = not any(w in text_b.lower() for w in ["silt", "high cost", "impurities", "illegal", "weak", "bad", "mistake", "contain", "cracks", "dredging"])
                    icon = "✔" if is_good else "✖"
                    icon_color = (0, 230, 118, pt_alpha) if is_good else (255, 61, 0, pt_alpha)
                    
                    draw.text((right_center - 130 + slide_offset, y), icon, font=pt_font, fill=icon_color)
                    draw.text((right_center - 95 + slide_offset, y), text_b, font=pt_font, fill=(230, 230, 230, pt_alpha))

    def _draw_ratio(self, draw, f, details, alpha):
        """Render ingredients and parts in a horizontal recipe/ratio layout."""
        mix_name = details.get("mix_name", "Concrete Mix")
        ratio_str = details.get("ratio", "1:2:4")
        ingredients = details.get("ingredients", [])
        
        # 1. Title of the Mix
        mix_font = self._select_font(mix_name, 34)
        bbox_mix = draw.textbbox((0, 0), f"{mix_name} ({ratio_str})", font=mix_font)
        draw.text((540 - (bbox_mix[2] - bbox_mix[0])//2, 470), f"{mix_name} ({ratio_str})", font=mix_font, fill=(255, 255, 255, alpha))
        
        # Jars coordinates
        num_items = len(ingredients)
        if num_items == 0:
            return
            
        spacing = 900 // num_items
        jar_w = 160
        jar_h = 240
        start_x = 540 - (spacing * (num_items - 1)) // 2
        
        jar_base_y = 860
        
        for idx, ing in enumerate(ingredients):
            name = ing.get("name", "Ingredient")
            parts = ing.get("parts", 1.0)
            color_name = ing.get("color", "grey").lower()
            
            # Determine color
            if "yellow" in color_name or "sand" in name.lower():
                fill_color = (220, 180, 80)
                stroke_color = (255, 220, 120)
            elif "grey" in color_name or "cement" in name.lower():
                fill_color = (120, 125, 130)
                stroke_color = (200, 205, 210)
            elif "dark_grey" in color_name or "gravel" in name.lower() or "aggregate" in name.lower() or "stone" in name.lower():
                fill_color = (70, 75, 80)
                stroke_color = (130, 135, 140)
            else: # blue/water
                fill_color = (0, 180, 216)
                stroke_color = (144, 224, 239)
                
            x_center = start_x + idx * spacing
            
            # Jar outline coordinates
            jx1 = x_center - jar_w // 2
            jy1 = jar_base_y - jar_h
            jx2 = x_center + jar_w // 2
            jy2 = jar_base_y
            
            # 2. Draw Jar Outline
            draw.rounded_rectangle(
                [jx1, jy1, jx2, jy2],
                radius=15,
                fill=None,
                outline=(255, 255, 255, int(100 * alpha/255)),
                width=3
            )
            
            # Draw Jar Base shading
            draw.line([jx1 + 10, jy2 - 4, jx2 - 10, jy2 - 4], fill=(255, 255, 255, int(40 * alpha/255)), width=2)
            
            # 3. Filling Animation (Staggered filling based on f)
            # Each jar fills in 25 frames
            start_f = idx * 25
            t_fill = min(max((f - start_f) / 25.0, 0.0), 1.0)
            
            fill_h = int(jar_h * 0.85 * t_fill) # fills up to 85% of jar height
            if fill_h > 0:
                fy1 = jy2 - fill_h
                
                # Draw particles / solid block
                if "aggregate" in name.lower() or "gravel" in name.lower() or "stone" in name.lower():
                    # Draw stones block
                    draw.rounded_rectangle([jx1 + 5, fy1, jx2 - 5, jy2 - 5], radius=10, fill=(fill_color[0], fill_color[1], fill_color[2], int(160 * alpha/255)))
                    # Add tiny aggregate details
                    for ox in [-40, -10, 20, 40]:
                        for oy in [-fill_h//2, -15, 15]:
                            if jy2 + oy < jy2 - 10 and jy2 + oy > fy1 + 10:
                                draw.ellipse([x_center + ox - 8, jy2 + oy - 8, x_center + ox + 8, jy2 + oy + 8], fill=stroke_color + (int(200 * alpha/255),))
                else:
                    draw.rounded_rectangle(
                        [jx1 + 5, fy1, jx2 - 5, jy2 - 5],
                        radius=10,
                        fill=(fill_color[0], fill_color[1], fill_color[2], int(180 * alpha/255))
                    )
            
            # 4. Draw ingredient text details (Labels fade in)
            t_lbl = min(max((f - start_f - 10) / 15.0, 0.0), 1.0)
            lbl_alpha = int(255 * t_lbl)
            
            if lbl_alpha > 0:
                label_font = self._select_font(name, 28)
                part_font = self._get_font(32)
                
                # Ingredient Name
                bbox_n = draw.textbbox((0, 0), name, font=label_font)
                draw.text((x_center - (bbox_n[2] - bbox_n[0])//2, jy2 + 25), name, font=label_font, fill=(255, 255, 255, lbl_alpha))
                
                # Proportions (e.g. "1.5 Parts" or "1 Bag")
                parts_label = f"{parts} PART" if parts == 1.0 else f"{parts} PARTS"
                if "cement" in name.lower() and parts == 1.0:
                    parts_label = "1 BAG"
                bbox_p = draw.textbbox((0, 0), parts_label, font=part_font)
                draw.text((x_center - (bbox_p[2] - bbox_p[0])//2, jy1 - 50), parts_label, font=part_font, fill=(255, 215, 0, lbl_alpha))
                
            # Draw Plus symbols between jars
            if idx < num_items - 1:
                plus_x = x_center + spacing // 2
                plus_y = jar_base_y - jar_h // 2
                t_plus = min(max((f - (start_f + 15)) / 15.0, 0.0), 1.0)
                plus_alpha = int(255 * t_plus)
                if plus_alpha > 0:
                    plus_font = self._get_font(44)
                    draw.text((plus_x - 15, plus_y - 25), "+", font=plus_font, fill=(0, 229, 255, plus_alpha))

        # Final aggregate mix label at the bottom (Fades in at the end)
        t_final = min(max((f - (num_items * 25)) / 20.0, 0.0), 1.0)
        final_alpha = int(255 * t_final)
        if final_alpha > 0:
            tip_text = "சரியான விகிதம் வலிமையான கட்டிடத்தை தரும்!"
            tip_font = self._select_font(tip_text, 28)
            bbox_t = draw.textbbox((0, 0), tip_text, font=tip_font)
            draw.text((540 - (bbox_t[2] - bbox_t[0])//2, jar_base_y + 110), tip_text, font=tip_font, fill=(0, 230, 118, final_alpha))

    def _draw_structural(self, draw, f, details, alpha):
        """Draw dynamic blueprint/structural diagrams (line-by-line animations)."""
        diag_type = details.get("diagram_type", "footing").lower()
        labels = details.get("labels", [])
        
        # Draw coordinate grids and outlines
        t_sketch = min(f / 45.0, 1.0) # 1.5 seconds sketch
        sketch_alpha = int(255 * t_sketch)
        
        if diag_type == "footing" or diag_type == "foundation":
            # Footing Slab: X from 250 to 830, Y from 920 to 1040
            # Column: X from 470 to 610, Y from 460 to 920
            # Ground line: Y = 700, X from 150 to 930
            
            # 1. Draw ground level line
            ground_y = 700
            gx1, gx2 = 150, 930
            curr_gx2 = gx1 + int((gx2 - gx1) * min(f / 15.0, 1.0))
            draw.line([gx1, ground_y, curr_gx2, ground_y], fill=(139, 69, 19, sketch_alpha), width=4)
            
            # Ground hatch marks
            if f >= 10:
                t_hatch = min((f - 10) / 10.0, 1.0)
                for hx in range(180, 900, 60):
                    if hx < gx1 + (gx2-gx1)*min((f-5)/15.0, 1.0):
                        draw.line([hx, ground_y, hx - 15, ground_y + 15], fill=(139, 69, 19, int(100 * t_hatch)), width=2)
            
            # 2. Draw Footing Slab outline
            if f >= 15:
                t_foot = min((f - 15) / 20.0, 1.0)
                fx1, fy1, fx2, fy2 = 250, 920, 830, 1040
                draw.rectangle([fx1, fy1, fx2, fy2], fill=(100, 105, 110, int(80 * t_foot)), outline=(200, 205, 210, int(255 * t_foot)), width=3)
            
            # 3. Draw Column rising up
            if f >= 25:
                t_col = min((f - 25) / 20.0, 1.0)
                cx1, cy1, cx2, cy2 = 470, 460, 610, 920
                draw.rectangle([cx1, cy1, cx2, cy2], fill=(120, 125, 130, int(80 * t_col)), outline=(200, 205, 210, int(255 * t_col)), width=3)
                
            # 4. Draw Steel reinforcement cage
            if f >= 35:
                t_steel = min((f - 35) / 20.0, 1.0)
                steel_alpha = int(255 * t_steel)
                rx_left = 500
                rx_right = 580
                ry_top = 480
                ry_bot = 1000
                
                # Left rebar with L-bend
                curr_y_bot = ry_top + int((ry_bot - ry_top) * t_steel)
                draw.line([rx_left, ry_top, rx_left, curr_y_bot], fill=(255, 102, 0, steel_alpha), width=4)
                if t_steel >= 0.9:
                    draw.line([rx_left, ry_bot, rx_left + 60, ry_bot], fill=(255, 102, 0, steel_alpha), width=4)
                    
                # Right rebar with L-bend
                draw.line([rx_right, ry_top, rx_right, curr_y_bot], fill=(255, 102, 0, steel_alpha), width=4)
                if t_steel >= 0.9:
                    draw.line([rx_right, ry_bot, rx_right - 60, ry_bot], fill=(255, 102, 0, steel_alpha), width=4)
                
                # Stirrup Ties
                if t_steel >= 0.5:
                    t_stir = min((f - 45) / 15.0, 1.0)
                    stir_alpha = int(255 * t_stir)
                    for sy in range(520, 900, 70):
                        draw.line([rx_left - 5, sy, rx_right + 5, sy], fill=(255, 140, 0, stir_alpha), width=2)
                        draw.line([rx_left - 5, sy, rx_left - 5, sy+5], fill=(255, 140, 0, stir_alpha), width=2)
                        draw.line([rx_right + 5, sy, rx_right + 5, sy+5], fill=(255, 140, 0, stir_alpha), width=2)

        elif diag_type == "brick_wall":
            # Draw layers of red brick wall
            brick_h = 45
            brick_w = 110
            mortar = 6
            start_y = 960
            start_x = 240
            
            # Foundations slab at bottom
            draw.rectangle([180, 1000, 900, 1060], fill=(80, 85, 90, sketch_alpha), outline=(200, 205, 210, sketch_alpha), width=3)
            
            # Render bricks row-by-row
            for row in range(7):
                row_y = start_y - row * (brick_h + mortar)
                start_f = row * 10
                t_row = min(max((f - start_f) / 10.0, 0.0), 1.0)
                row_alpha = int(255 * t_row)
                
                if row_alpha > 0:
                    offset_x = (brick_w // 2) if (row % 2 == 1) else 0
                    
                    for col in range(6):
                        bx1 = start_x + col * (brick_w + mortar) - offset_x
                        by1 = row_y
                        bx2 = bx1 + brick_w
                        by2 = row_y + brick_h
                        
                        if bx1 < 190: 
                            bx1 = 190
                        if bx2 > 890: 
                            bx2 = 890
                        if bx1 < bx2:
                            draw.rectangle(
                                [bx1, by1, bx2, by2],
                                fill=(188, 74, 60, int(180 * t_row)),
                                outline=(255, 120, 100, row_alpha),
                                width=2
                            )
        else:
            # Default blueprint grid
            draw.line([200, 480, 880, 480], fill=(0, 229, 255, int(100 * alpha/255)), width=2)
            draw.line([200, 1050, 880, 1050], fill=(0, 229, 255, int(100 * alpha/255)), width=2)
            draw.rectangle([340, 500, 740, 1030], fill=(50, 55, 60, int(60 * alpha/255)), outline=(0, 229, 255, alpha), width=3)
            for rx in range(380, 740, 80):
                draw.line([rx, 500, rx, 1030], fill=(255, 215, 0, int(100 * alpha/255)), width=2)

        # 5. Draw Dimension Lines and Labels
        t_label = min(max((f - 50) / 20.0, 0.0), 1.0)
        label_alpha = int(255 * t_label)
        
        if label_alpha > 0:
            lbl_font = self._select_font(' '.join(l.get('text','') for l in labels), 28)
            dim_font = self._get_font(30)
            
            if diag_type == "footing" or diag_type == "foundation":
                # Depth arrow on left
                arrow_x = 200
                draw.line([arrow_x, 700, arrow_x, 1040], fill=(0, 229, 255, label_alpha), width=3)
                draw.line([arrow_x, 700, arrow_x - 10, 715], fill=(0, 229, 255, label_alpha), width=3)
                draw.line([arrow_x, 700, arrow_x + 10, 715], fill=(0, 229, 255, label_alpha), width=3)
                draw.line([arrow_x, 1040, arrow_x - 10, 1025], fill=(0, 229, 255, label_alpha), width=3)
                draw.line([arrow_x, 1040, arrow_x + 10, 1025], fill=(0, 229, 255, label_alpha), width=3)
                
                bbox_dl = draw.textbbox((0, 0), "5 FEET DEPTH", font=dim_font)
                draw.text((arrow_x - (bbox_dl[2] - bbox_dl[0]) - 20, 850), "5 FEET DEPTH", font=dim_font, fill=(0, 229, 255, label_alpha))
                
                # Column Width Dimension
                cw_y = 420
                draw.line([470, cw_y, 610, cw_y], fill=(0, 229, 255, label_alpha), width=3)
                draw.line([470, cw_y, 485, cw_y - 10], fill=(0, 229, 255, label_alpha), width=3)
                draw.line([470, cw_y, 485, cw_y + 10], fill=(0, 229, 255, label_alpha), width=3)
                draw.line([610, cw_y, 595, cw_y - 10], fill=(0, 229, 255, label_alpha), width=3)
                draw.line([610, cw_y, 595, cw_y + 10], fill=(0, 229, 255, label_alpha), width=3)
                draw.text((505, cw_y - 45), "1.5 FT", font=dim_font, fill=(0, 229, 255, label_alpha))
                
            for idx, lbl in enumerate(labels):
                text = lbl.get("text", "")
                lx = lbl.get("x", 540)
                ly = lbl.get("y", 800)
                
                draw.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=(255, 215, 0, label_alpha))
                draw.ellipse([lx - 15, ly - 15, lx + 15, ly + 15], fill=None, outline=(255, 215, 0, int(80 * t_label)), width=2)
                
                pointer_dest_x = lx + (100 if lx < 540 else -100)
                pointer_dest_y = ly - 70
                draw.line([lx, ly, pointer_dest_x, pointer_dest_y], fill=(255, 255, 255, int(150 * t_label)), width=2)
                
                bbox_lbl = draw.textbbox((0, 0), text, font=lbl_font)
                text_x = pointer_dest_x if lx < 540 else (pointer_dest_x - (bbox_lbl[2] - bbox_lbl[0]))
                draw.text((text_x, pointer_dest_y - 40), text, font=lbl_font, fill=(255, 255, 255, label_alpha))

    def _draw_progress(self, draw, f, details, alpha):
        """Render circular or timeline progress indicators (e.g. Curing days)."""
        target_label = details.get("target_label", "Curing Duration")
        val_str = details.get("value", "7 Days")
        milestones = details.get("milestones", [])
        
        center_x, center_y = 540, 680
        radius = 180
        width = 25
        
        # Outer Ring Outline
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            fill=None,
            outline=(100, 105, 110, int(100 * alpha/255)),
            width=width
        )
        
        # 1. Sweep Progress Arc
        t_sweep = min(f / 45.0, 1.0)
        angle = int(360 * t_sweep)
        
        if angle > 0:
            draw.arc(
                [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
                start=-90,
                end=-90 + angle,
                fill=(255, 215, 0, alpha),
                width=width
            )
            
        # 2. Draw text inside circle
        t_text = min(max((f - 10) / 20.0, 0.0), 1.0)
        val_alpha = int(255 * t_text)
        
        if val_alpha > 0:
            val_font = self._get_font(60)
            lbl_font = self._select_font(target_label, 28)
            
            bbox_v = draw.textbbox((0, 0), val_str, font=val_font)
            draw.text((center_x - (bbox_v[2] - bbox_v[0])//2, center_y - 45), val_str, font=val_font, fill=(0, 229, 255, val_alpha))
            
            bbox_l = draw.textbbox((0, 0), target_label, font=lbl_font)
            draw.text((center_x - (bbox_l[2] - bbox_l[0])//2, center_y + 35), target_label, font=lbl_font, fill=(200, 200, 200, val_alpha))

        # 3. Draw milestones as items below
        ms_start_y = center_y + radius + 80
        ms_font = self._select_font(' '.join(milestones), 28)
        
        for idx, ms in enumerate(milestones):
            start_f = 35 + idx * 20
            t_ms = min(max((f - start_f) / 15.0, 0.0), 1.0)
            ms_alpha = int(255 * t_ms)
            
            if ms_alpha > 0:
                y = ms_start_y + idx * 80
                slide = int((1.0 - t_ms) * -20)
                
                draw.text((200 + slide, y), "✔", font=ms_font, fill=(0, 230, 118, ms_alpha))
                draw.text((245 + slide, y), ms, font=ms_font, fill=(240, 240, 240, ms_alpha))
                
                if idx < len(milestones) - 1:
                    draw.line([200, y + 55, 880, y + 55], fill=(255, 255, 255, int(20 * t_ms)), width=1)

    def _draw_warning(self, draw, f, details, alpha):
        """Render structural defect highlights (magnifying target, flashing warning, and remedy text)."""
        defect = details.get("defect_name", "Defect")
        conseq = details.get("consequence", "Damage risk")
        fix = details.get("fix", "Standard repair")
        
        beam_x1, beam_y1 = 200, 680
        beam_x2, beam_y2 = 880, 860
        
        # 1. Draw Concrete Beam outline
        draw.rectangle(
            [beam_x1, beam_y1, beam_x2, beam_y2],
            fill=(100, 105, 110, int(100 * alpha/255)),
            outline=(200, 205, 210, alpha),
            width=3
        )
        
        for ox in range(250, 850, 100):
            draw.ellipse([ox, beam_y1 + 40, ox + 15, beam_y1 + 55], fill=(130, 135, 140, int(80 * alpha/255)))
            draw.polygon([(ox+40, beam_y1+100), (ox+50, beam_y1+80), (ox+60, beam_y1+110)], fill=(70, 75, 80, int(80 * alpha/255)))
            
        # 2. Draw defect: cracks or honeycombing in the middle
        defect_alpha = int(255 * min(max((f - 15) / 15.0, 0.0), 1.0))
        target_x, target_y = 540, 770
        
        if defect_alpha > 0:
            if "honeycomb" in defect.lower() or "void" in defect.lower():
                for dx, dy in [(-30, 0), (-10, -20), (10, 10), (30, -10), (0, 20), (-20, 15), (20, -15)]:
                    cx, cy = target_x + dx, target_y + dy
                    draw.ellipse([cx-12, cy-12, cx+12, cy+12], fill=(40, 45, 50, defect_alpha))
                    draw.ellipse([cx-8, cy-8, cx+8, cy+8], fill=(255, 69, 0, int(100 * defect_alpha/255)))
            else:
                draw.line([target_x - 70, beam_y1, target_x - 30, target_y - 20], fill=(255, 61, 0, defect_alpha), width=4)
                draw.line([target_x - 30, target_y - 20, target_x + 10, target_y + 20], fill=(255, 61, 0, defect_alpha), width=4)
                draw.line([target_x + 10, target_y + 20, target_x + 30, beam_y2], fill=(255, 61, 0, defect_alpha), width=4)
                draw.line([target_x - 30, target_y - 20, target_x - 10, target_y + 10], fill=(255, 61, 0, defect_alpha), width=3)
        
        # 3. Pulsing Red Target Overlay
        if f >= 30:
            pulse_frame = f - 30
            pulse_rad = int(55 + 20 * math.sin(pulse_frame * 0.3))
            pulse_alpha = int(180 + 75 * math.sin(pulse_frame * 0.3))
            
            draw.ellipse(
                [target_x - pulse_rad, target_y - pulse_rad, target_x + pulse_rad, target_y + pulse_rad],
                fill=None,
                outline=(255, 61, 0, pulse_alpha),
                width=3
            )
            draw.line([target_x - pulse_rad - 10, target_y, target_x - 10, target_y], fill=(255, 61, 0, pulse_alpha), width=2)
            draw.line([target_x + 10, target_y, target_x + pulse_rad + 10, target_y], fill=(255, 61, 0, pulse_alpha), width=2)
            draw.line([target_x, target_y - pulse_rad - 10, target_x, target_y - 10], fill=(255, 61, 0, pulse_alpha), width=2)
            draw.line([target_x, target_y + 10, target_x, target_y + pulse_rad + 10], fill=(255, 61, 0, pulse_alpha), width=2)

        # 4. Warning Icon at Top Center
        t_icon = min(max((f - 10) / 15.0, 0.0), 1.0)
        icon_alpha = int(255 * t_icon)
        if icon_alpha > 0:
            icon_font = self._get_font(44)
            tx, ty = 540, 480
            draw.polygon([(tx, ty - 35), (tx - 40, ty + 35), (tx + 40, ty + 35)], fill=(255, 61, 0, int(40 * t_icon)), outline=(255, 61, 0, icon_alpha), width=3)
            draw.text((tx - 6, ty - 12), "!", font=icon_font, fill=(255, 61, 0, icon_alpha))

        # 5. Cause and Remedy Boxes
        t_box = min(max((f - 40) / 20.0, 0.0), 1.0)
        box_alpha = int(255 * t_box)
        
        if box_alpha > 0:
            info_font = self._select_font(conseq + fix, 28)
            bold_font = self._get_font(28, prefer_tamil=True)  # Tamil labels: விளைவு, தீர்வு
            
            box_y = beam_y2 + 45
            slide = int((1.0 - t_box) * -20)
            
            defect_font = self._select_font(defect, 34)
            bbox_d = draw.textbbox((0, 0), defect.upper(), font=defect_font)
            draw.text((540 - (bbox_d[2] - bbox_d[0])//2, box_y - 45 + slide), defect.upper(), font=defect_font, fill=(255, 61, 0, box_alpha))
            
            draw.text((150 + slide, box_y + 15), "விளைவு:", font=bold_font, fill=(255, 215, 0, box_alpha))
            draw.text((290 + slide, box_y + 15), conseq, font=info_font, fill=(240, 240, 240, box_alpha))
            
            draw.text((150 + slide, box_y + 90), "தீர்வு:", font=bold_font, fill=(0, 230, 118, box_alpha))
            draw.text((290 + slide, box_y + 90), fix, font=info_font, fill=(240, 240, 240, box_alpha))

    def _draw_default(self, draw, f, title, details, alpha):
        """Standard backup details display."""
        lines = []
        for k, v in details.items():
            if isinstance(v, list):
                v_str = ", ".join(map(str, v))
            else:
                v_str = str(v)
            lines.append(f"{k.capitalize()}: {v_str}")
            
        pt_font = self._select_font(' '.join(str(v) for v in details.values()), 28)
        start_y = 520
        
        for idx, line in enumerate(lines[:6]):
            t_line = min(max((f - idx * 15) / 15.0, 0.0), 1.0)
            line_alpha = int(255 * t_line)
            
            if line_alpha > 0:
                y = start_y + idx * 90
                slide = int((1.0 - t_line) * -30)
                draw.text((120 + slide, y), "•", font=pt_font, fill=(255, 215, 0, line_alpha))
                draw.text((160 + slide, y), line, font=pt_font, fill=(240, 240, 240, line_alpha))
