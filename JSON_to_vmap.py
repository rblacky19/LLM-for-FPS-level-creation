import json
import uuid
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Tuple, List

# Default configuration
DEFAULT_CS2_PATH = r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\content\csgo_addons\test\maps"
DEFAULT_JSON_PATH = ""
CONFIG_FILE = "vmap_generator_config.json"


class VMAPGenerator:
    """Generate CS2 VMAP files from simplified level descriptions"""
    
    def __init__(self):
        self.node_counter = 1
        
    def generate_uuid(self) -> str:
        """Generate a random UUID for VMAP elements"""
        return str(uuid.uuid4())
    
    def get_next_node_id(self) -> int:
        """Get next unique node ID"""
        node_id = self.node_counter
        self.node_counter += 1
        return node_id
    
    def generate_texcoords(self, width: float, depth: float, height: float, uv_scale: float = 128.0) -> List[str]:
        """
        Generate properly scaled UV coordinates for a box mesh.
        
        Args:
            width, depth, height: Box dimensions
            uv_scale: Units per UV tile (default 128, use 64 for smaller textures)
        """
        hw, hd, hh = width/2, depth/2, height/2
        
        # The 8 geometric vertex positions (same order as in create_box_mesh)
        vertices = [
            (-hw, -hd, hh),   # v0: front-left-top
            (hw, -hd, hh),    # v1: front-right-top
            (-hw, hd, hh),    # v2: back-left-top
            (hw, hd, -hh),    # v3: back-right-bottom
            (-hw, hd, -hh),   # v4: back-left-bottom
            (hw, hd, hh),     # v5: back-right-top
            (hw, -hd, -hh),   # v6: front-right-bottom
            (-hw, -hd, -hh),  # v7: front-left-bottom
        ]
        
        # Mapping from face-vertex index (0-23) to geometric vertex index (0-7)
        # Derived from the half-edge mesh topology
        fv_to_v = {
            0: 0, 1: 1, 2: 1, 3: 5, 4: 5, 5: 2, 6: 1, 7: 6,
            8: 4, 9: 3, 10: 3, 11: 6, 12: 6, 13: 7, 14: 3, 15: 5,
            16: 4, 17: 7, 18: 7, 19: 0, 20: 0, 21: 2, 22: 2, 23: 4
        }
        
        # Normal direction for each face-vertex (determines which face it belongs to)
        # 0=(-Y), 1=(+Z), 2=(+X), 3=(+Z), 4=(+Y), 5=(+Z), etc.
        normals = [
            (0, -1, 0),  # 0: -Y
            (0, 0, 1),   # 1: +Z
            (1, 0, 0),   # 2: +X
            (0, 0, 1),   # 3: +Z
            (0, 1, 0),   # 4: +Y
            (0, 0, 1),   # 5: +Z
            (0, -1, 0),  # 6: -Y
            (1, 0, 0),   # 7: +X
            (0, 1, 0),   # 8: +Y
            (0, 0, -1),  # 9: -Z
            (1, 0, 0),   # 10: +X
            (0, 0, -1),  # 11: -Z
            (0, -1, 0),  # 12: -Y
            (0, 0, -1),  # 13: -Z
            (0, 1, 0),   # 14: +Y
            (1, 0, 0),   # 15: +X
            (0, 0, -1),  # 16: -Z
            (-1, 0, 0),  # 17: -X
            (0, -1, 0),  # 18: -Y
            (-1, 0, 0),  # 19: -X
            (0, 0, 1),   # 20: +Z
            (-1, 0, 0),  # 21: -X
            (0, 1, 0),   # 22: +Y
            (-1, 0, 0),  # 23: -X
        ]
        
        uvs = []
        for fv in range(24):
            v_idx = fv_to_v[fv]
            x, y, z = vertices[v_idx]
            nx, ny, nz = normals[fv]
            
            # Project vertex position to UV based on face normal
            # Offset by half-dimension so UVs start at 0 instead of centered around 0
            if ny != 0:  # -Y or +Y face (front/back)
                u = (x + hw) / uv_scale
                v = (hh - z) / uv_scale
            elif nx != 0:  # -X or +X face (left/right)
                u = (y + hd) / uv_scale
                v = (hh - z) / uv_scale
            else:  # -Z or +Z face (bottom/top)
                u = (x + hw) / uv_scale
                v = (hd - y) / uv_scale
            
            uvs.append(f"{u} {v}")
        
        return uvs
    
    def create_box_mesh(self, width: float, depth: float, height: float, 
                       origin: Tuple[float, float, float] = (0, 0, 0),
                       material: str = "materials/dev/reflectivity_30.vmat",
                       uv_scale: float = 128.0) -> str:
        """Generate a box mesh in VMAP format with proper UV scaling
        
        Args:
            width, depth, height: Box dimensions
            origin: World position
            material: Material path
            uv_scale: Units per UV tile (default 128, use 64 for smaller textures like crates)
        """
        hw, hd, hh = width/2, depth/2, height/2
        ox, oy, oz = origin
        
        # Vertices are relative to LOCAL origin (0,0,0)
        # The origin property will position the mesh in world space
        vertices = [
            f"{-hw} {-hd} {hh}",
            f"{hw} {-hd} {hh}",
            f"{-hw} {hd} {hh}",
            f"{hw} {hd} {-hh}",
            f"{-hw} {hd} {-hh}",
            f"{hw} {hd} {hh}",
            f"{hw} {-hd} {-hh}",
            f"{-hw} {-hd} {-hh}"
        ]
        
        node_id = self.get_next_node_id()
        
        # Generate properly scaled UV coordinates
        texcoords = self.generate_texcoords(width, depth, height, uv_scale)
        texcoord_str = ',\n\t\t\t\t\t\t\t\t\t'.join([f'"{uv}"' for uv in texcoords])
        
        mesh = f'''\t\t\t"CMapMesh"
\t\t\t{{
\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t"nodeID" "int" "{node_id}"
\t\t\t\t"referenceID" "uint64" "0x{node_id:016x}"
\t\t\t\t"children" "element_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"variableTargetKeys" "string_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"variableNames" "string_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"meshData" "CDmePolygonMesh"
\t\t\t\t{{
\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t"name" "string" "meshData"
\t\t\t\t\t"vertexEdgeIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"0", "1", "22", "15", "8", "14", "6", "18"
\t\t\t\t\t]
\t\t\t\t\t"vertexDataIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"0", "1", "2", "3", "4", "5", "6", "7"
\t\t\t\t\t]
\t\t\t\t\t"edgeVertexIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"1", "0", "5", "1", "2", "5", "1", "6", "3", "4", "6", "3",
\t\t\t\t\t\t"7", "6", "3", "5", "7", "4", "0", "7", "2", "0", "4", "2"
\t\t\t\t\t]
\t\t\t\t\t"edgeOppositeIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"1", "0", "3", "2", "5", "4", "7", "6", "9", "8", "11", "10",
\t\t\t\t\t\t"13", "12", "15", "14", "17", "16", "19", "18", "21", "20", "23", "22"
\t\t\t\t\t]
\t\t\t\t\t"edgeNextIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"2", "19", "4", "7", "21", "14", "1", "11", "10", "23", "12", "15",
\t\t\t\t\t\t"17", "6", "9", "3", "18", "8", "20", "13", "22", "0", "16", "5"
\t\t\t\t\t]
\t\t\t\t\t"edgeFaceIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"0", "5", "0", "3", "0", "4", "5", "3", "1", "4", "1", "3",
\t\t\t\t\t\t"1", "5", "4", "3", "2", "1", "2", "5", "2", "0", "2", "4"
\t\t\t\t\t]
\t\t\t\t\t"edgeDataIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"0", "0", "1", "1", "2", "2", "3", "3", "4", "4", "5", "5",
\t\t\t\t\t\t"6", "6", "7", "7", "8", "8", "9", "9", "10", "10", "11", "11"
\t\t\t\t\t]
\t\t\t\t\t"edgeVertexDataIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"1", "0", "3", "2", "5", "4", "6", "7", "9", "8", "11", "10",
\t\t\t\t\t\t"13", "12", "14", "15", "17", "16", "19", "18", "21", "20", "23", "22"
\t\t\t\t\t]
\t\t\t\t\t"faceEdgeIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"21", "17", "22", "15", "14", "6"
\t\t\t\t\t]
\t\t\t\t\t"faceDataIndices" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"0", "1", "2", "3", "4", "5"
\t\t\t\t\t]
\t\t\t\t\t"materials" "string_array" 
\t\t\t\t\t[
\t\t\t\t\t\t"{material}"
\t\t\t\t\t]
\t\t\t\t\t"vertexData" "CDmePolygonMeshDataArray"
\t\t\t\t\t{{
\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t"size" "int" "8"
\t\t\t\t\t\t"streams" "element_array" 
\t\t\t\t\t\t[
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "position:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "position"
\t\t\t\t\t\t\t\t"semanticName" "string" "position"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "3"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "vector3_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"{vertices[0]}",
\t\t\t\t\t\t\t\t\t"{vertices[1]}",
\t\t\t\t\t\t\t\t\t"{vertices[2]}",
\t\t\t\t\t\t\t\t\t"{vertices[3]}",
\t\t\t\t\t\t\t\t\t"{vertices[4]}",
\t\t\t\t\t\t\t\t\t"{vertices[5]}",
\t\t\t\t\t\t\t\t\t"{vertices[6]}",
\t\t\t\t\t\t\t\t\t"{vertices[7]}"
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t]
\t\t\t\t\t}}
\t\t\t\t\t"faceVertexData" "CDmePolygonMeshDataArray"
\t\t\t\t\t{{
\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t"size" "int" "24"
\t\t\t\t\t\t"streams" "element_array" 
\t\t\t\t\t\t[
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "texcoord:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "texcoord"
\t\t\t\t\t\t\t\t"semanticName" "string" "texcoord"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "1"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "vector2_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t{texcoord_str}
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}},
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "normal:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "normal"
\t\t\t\t\t\t\t\t"semanticName" "string" "normal"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "1"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "vector3_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"0 -1 0", "0 0 1", "1 0 0", "0 0 1", "0 1 0", "0 0 1",
\t\t\t\t\t\t\t\t\t"0 -1 0", "1 0 0", "0 1 0", "0 0 -1", "1 0 0", "0 0 -1",
\t\t\t\t\t\t\t\t\t"0 -1 0", "0 0 -1", "0 1 0", "1 0 0", "0 0 -1", "-1 0 0",
\t\t\t\t\t\t\t\t\t"0 -1 0", "-1 0 0", "0 0 1", "-1 0 0", "0 1 0", "-1 0 0"
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}},
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "tangent:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "tangent"
\t\t\t\t\t\t\t\t"semanticName" "string" "tangent"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "1"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "vector4_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"1 0 0 -1", "1 0 0 -1", "0 1 0 -1", "1 0 0 -1", "1 0 0 1", "1 0 0 -1",
\t\t\t\t\t\t\t\t\t"1 0 0 -1", "0 1 0 -1", "1 0 0 1", "1 0 0 1", "0 1 0 -1", "1 0 0 1",
\t\t\t\t\t\t\t\t\t"1 0 0 -1", "1 0 0 1", "1 0 0 1", "0 1 0 -1", "1 0 0 1", "0 1 0 1",
\t\t\t\t\t\t\t\t\t"1 0 0 -1", "0 1 0 1", "1 0 0 -1", "0 1 0 1", "1 0 0 1", "0 1 0 1"
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t]
\t\t\t\t\t}}
\t\t\t\t\t"edgeData" "CDmePolygonMeshDataArray"
\t\t\t\t\t{{
\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t"size" "int" "12"
\t\t\t\t\t\t"streams" "element_array" 
\t\t\t\t\t\t[
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "flags:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "flags"
\t\t\t\t\t\t\t\t"semanticName" "string" "flags"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "3"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "int_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t]
\t\t\t\t\t}}
\t\t\t\t\t"faceData" "CDmePolygonMeshDataArray"
\t\t\t\t\t{{
\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t"size" "int" "6"
\t\t\t\t\t\t"streams" "element_array" 
\t\t\t\t\t\t[
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "textureScale:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "textureScale"
\t\t\t\t\t\t\t\t"semanticName" "string" "textureScale"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "0"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "vector2_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"0.125 0.125", "0.125 0.125", "0.125 0.125",
\t\t\t\t\t\t\t\t\t"0.125 0.125", "0.125 0.125", "0.125 0.125"
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}},
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "textureAxisU:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "textureAxisU"
\t\t\t\t\t\t\t\t"semanticName" "string" "textureAxisU"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "0"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "vector4_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"1 0 0 0", "1 0 0 0", "0 1 0 0",
\t\t\t\t\t\t\t\t\t"0 1 0 0", "1 0 0 0", "1 0 0 0"
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}},
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "textureAxisV:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "textureAxisV"
\t\t\t\t\t\t\t\t"semanticName" "string" "textureAxisV"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "0"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "vector4_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"0 -1 0 0", "0 -1 0 0", "0 0 -1 0",
\t\t\t\t\t\t\t\t\t"0 0 -1 0", "0 0 -1 0", "0 0 -1 0"
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}},
\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"name" "string" "materialindex:0"
\t\t\t\t\t\t\t\t"standardAttributeName" "string" "materialindex"
\t\t\t\t\t\t\t\t"semanticName" "string" "materialindex"
\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t"dataStateFlags" "int" "8"
\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t"data" "int_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"0", "0", "0", "0", "0", "0"
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t]
\t\t\t\t\t}}
\t\t\t\t}}
\t\t\t\t"origin" "vector3" "{ox} {oy} {oz}"
\t\t\t\t"angles" "qangle" "0 0 0"
\t\t\t\t"scales" "vector3" "1 1 1"
\t\t\t\t"bakelighting" "bool" "1"
\t\t\t\t"renderToCubemaps" "bool" "1"
\t\t\t\t"smoothingAngle" "float" "40"
\t\t\t\t"tintColor" "color" "255 255 255 255"
\t\t\t\t"renderAmt" "int" "255"
\t\t\t}}'''
        
        return mesh
    
    def create_entity(self, classname: str, origin: Tuple[float, float, float],
                     properties: Dict[str, str] = None,
                     angles: Tuple[float, float, float] = (0, 0, 0)) -> str:
        """Generate an entity in VMAP format"""
        node_id = self.get_next_node_id()
        ox, oy, oz = origin
        ang_x, ang_y, ang_z = angles
        
        props = {
            "classname": classname,
            "targetname": "",
            "priority": "0",
            "enabled": "1"
        }
        if properties:
            props.update(properties)
        
        prop_strings = []
        for key, value in props.items():
            prop_strings.append(f'\t\t\t\t\t"{key}" "string" "{value}"')
        
        entity = f'''\t\t\t"CMapEntity"
\t\t\t{{
\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t"nodeID" "int" "{node_id}"
\t\t\t\t"referenceID" "uint64" "0x{node_id:016x}"
\t\t\t\t"children" "element_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"variableTargetKeys" "string_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"variableNames" "string_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"relayPlugData" "DmePlugList"
\t\t\t\t{{
\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t"names" "string_array" 
\t\t\t\t\t[
\t\t\t\t\t]
\t\t\t\t\t"dataTypes" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t]
\t\t\t\t\t"plugTypes" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t]
\t\t\t\t\t"descriptions" "string_array" 
\t\t\t\t\t[
\t\t\t\t\t]
\t\t\t\t}}
\t\t\t\t"connectionsData" "element_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"entity_properties" "EditGameClassProps"
\t\t\t\t{{
\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
{chr(10).join(prop_strings)}
\t\t\t\t}}
\t\t\t\t"hitNormal" "vector3" "0 0 1"
\t\t\t\t"isProceduralEntity" "bool" "0"
\t\t\t\t"origin" "vector3" "{ox} {oy} {oz}"
\t\t\t\t"angles" "qangle" "{ang_x} {ang_y} {ang_z}"
\t\t\t\t"scales" "vector3" "1 1 1"
\t\t\t\t"transformLocked" "bool" "0"
\t\t\t\t"force_hidden" "bool" "0"
\t\t\t\t"editorOnly" "bool" "0"
\t\t\t}}'''
        
        return entity

    def create_brush_entity(self, classname: str, origin: Tuple[float, float, float],
                           width: float, depth: float, height: float,
                           properties: Dict[str, str] = None,
                           material: str = "materials/tools/toolstrigger.vmat") -> str:
        """Generate a brush entity (entity with mesh child) in VMAP format"""
        entity_node_id = self.get_next_node_id()
        mesh_node_id = self.get_next_node_id()
        ox, oy, oz = origin
        hw, hd, hh = width/2, depth/2, height/2
        
        props = {
            "classname": classname,
            "targetname": "",
        }
        if properties:
            props.update(properties)
        
        prop_strings = []
        for key, value in props.items():
            prop_strings.append(f'\t\t\t\t\t"{key}" "string" "{value}"')
        
        # Vertices for the mesh (local coordinates)
        vertices = [
            f"{-hw} {-hd} {hh}",
            f"{hw} {-hd} {hh}",
            f"{-hw} {hd} {hh}",
            f"{hw} {hd} {-hh}",
            f"{-hw} {hd} {-hh}",
            f"{hw} {hd} {hh}",
            f"{hw} {-hd} {-hh}",
            f"{-hw} {-hd} {-hh}"
        ]
        
        # Generate properly scaled UV coordinates
        texcoords = self.generate_texcoords(width, depth, height)
        texcoord_str = ',\n\t\t\t\t\t\t\t\t\t\t\t'.join([f'"{uv}"' for uv in texcoords])
        
        entity = f'''\t\t\t"CMapEntity"
\t\t\t{{
\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t"nodeID" "int" "{entity_node_id}"
\t\t\t\t"referenceID" "uint64" "0x{entity_node_id:016x}"
\t\t\t\t"children" "element_array" 
\t\t\t\t[
\t\t\t\t\t"CMapMesh"
\t\t\t\t\t{{
\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t"nodeID" "int" "{mesh_node_id}"
\t\t\t\t\t\t"referenceID" "uint64" "0x{mesh_node_id:016x}"
\t\t\t\t\t\t"children" "element_array" 
\t\t\t\t\t\t[
\t\t\t\t\t\t]
\t\t\t\t\t\t"variableTargetKeys" "string_array" 
\t\t\t\t\t\t[
\t\t\t\t\t\t]
\t\t\t\t\t\t"variableNames" "string_array" 
\t\t\t\t\t\t[
\t\t\t\t\t\t]
\t\t\t\t\t\t"meshData" "CDmePolygonMesh"
\t\t\t\t\t\t{{
\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t"name" "string" "meshData"
\t\t\t\t\t\t\t"vertexEdgeIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"0", "1", "22", "15", "8", "14", "6", "18"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"vertexDataIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"0", "1", "2", "3", "4", "5", "6", "7"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"edgeVertexIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"1", "0", "5", "1", "2", "5", "1", "6", "3", "4", "6", "3",
\t\t\t\t\t\t\t\t"7", "6", "3", "5", "7", "4", "0", "7", "2", "0", "4", "2"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"edgeOppositeIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"1", "0", "3", "2", "5", "4", "7", "6", "9", "8", "11", "10",
\t\t\t\t\t\t\t\t"13", "12", "15", "14", "17", "16", "19", "18", "21", "20", "23", "22"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"edgeNextIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"2", "19", "4", "7", "21", "14", "1", "11", "10", "23", "12", "15",
\t\t\t\t\t\t\t\t"17", "6", "9", "3", "18", "8", "20", "13", "22", "0", "16", "5"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"edgeFaceIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"0", "5", "0", "3", "0", "4", "5", "3", "1", "4", "1", "3",
\t\t\t\t\t\t\t\t"1", "5", "4", "3", "2", "1", "2", "5", "2", "0", "2", "4"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"edgeDataIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"0", "0", "1", "1", "2", "2", "3", "3", "4", "4", "5", "5",
\t\t\t\t\t\t\t\t"6", "6", "7", "7", "8", "8", "9", "9", "10", "10", "11", "11"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"edgeVertexDataIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"1", "0", "3", "2", "5", "4", "6", "7", "9", "8", "11", "10",
\t\t\t\t\t\t\t\t"13", "12", "14", "15", "17", "16", "19", "18", "21", "20", "23", "22"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"faceEdgeIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"21", "17", "22", "15", "14", "6"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"faceDataIndices" "int_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"0", "1", "2", "3", "4", "5"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"materials" "string_array" 
\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t"{material}"
\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t"vertexData" "CDmePolygonMeshDataArray"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"size" "int" "8"
\t\t\t\t\t\t\t\t"streams" "element_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t\t\t"name" "string" "position:0"
\t\t\t\t\t\t\t\t\t\t"standardAttributeName" "string" "position"
\t\t\t\t\t\t\t\t\t\t"semanticName" "string" "position"
\t\t\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t\t\t"dataStateFlags" "int" "3"
\t\t\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t\t\t"data" "vector3_array" 
\t\t\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t\t\t"{vertices[0]}",
\t\t\t\t\t\t\t\t\t\t\t"{vertices[1]}",
\t\t\t\t\t\t\t\t\t\t\t"{vertices[2]}",
\t\t\t\t\t\t\t\t\t\t\t"{vertices[3]}",
\t\t\t\t\t\t\t\t\t\t\t"{vertices[4]}",
\t\t\t\t\t\t\t\t\t\t\t"{vertices[5]}",
\t\t\t\t\t\t\t\t\t\t\t"{vertices[6]}",
\t\t\t\t\t\t\t\t\t\t\t"{vertices[7]}"
\t\t\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t"faceVertexData" "CDmePolygonMeshDataArray"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"size" "int" "24"
\t\t\t\t\t\t\t\t"streams" "element_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t\t\t"name" "string" "texcoord:0"
\t\t\t\t\t\t\t\t\t\t"standardAttributeName" "string" "texcoord"
\t\t\t\t\t\t\t\t\t\t"semanticName" "string" "texcoord"
\t\t\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t\t\t"dataStateFlags" "int" "1"
\t\t\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t\t\t"data" "vector2_array" 
\t\t\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t\t\t{texcoord_str}
\t\t\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t"edgeData" "CDmePolygonMeshDataArray"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"size" "int" "12"
\t\t\t\t\t\t\t\t"streams" "element_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t"faceData" "CDmePolygonMeshDataArray"
\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t"size" "int" "6"
\t\t\t\t\t\t\t\t"streams" "element_array" 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"CDmePolygonMeshDataStream"
\t\t\t\t\t\t\t\t\t{{
\t\t\t\t\t\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t\t\t\t\t\t"name" "string" "textureScale:0"
\t\t\t\t\t\t\t\t\t\t"standardAttributeName" "string" "textureScale"
\t\t\t\t\t\t\t\t\t\t"semanticName" "string" "textureScale"
\t\t\t\t\t\t\t\t\t\t"semanticIndex" "int" "0"
\t\t\t\t\t\t\t\t\t\t"vertexBufferLocation" "int" "0"
\t\t\t\t\t\t\t\t\t\t"dataStateFlags" "int" "0"
\t\t\t\t\t\t\t\t\t\t"subdivisionBinding" "element" ""
\t\t\t\t\t\t\t\t\t\t"data" "vector2_array" 
\t\t\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t\t\t"0.125 0.125", "0.125 0.125", "0.125 0.125",
\t\t\t\t\t\t\t\t\t\t\t"0.125 0.125", "0.125 0.125", "0.125 0.125"
\t\t\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t}}
\t\t\t\t\t\t"origin" "vector3" "{ox} {oy} {oz}"
\t\t\t\t\t\t"angles" "qangle" "0 0 0"
\t\t\t\t\t\t"scales" "vector3" "1 1 1"
\t\t\t\t\t\t"bakelighting" "bool" "1"
\t\t\t\t\t\t"renderToCubemaps" "bool" "1"
\t\t\t\t\t\t"smoothingAngle" "float" "40"
\t\t\t\t\t\t"tintColor" "color" "255 255 255 255"
\t\t\t\t\t\t"renderAmt" "int" "255"
\t\t\t\t\t}}
\t\t\t\t]
\t\t\t\t"variableTargetKeys" "string_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"variableNames" "string_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"relayPlugData" "DmePlugList"
\t\t\t\t{{
\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t\t\t"names" "string_array" 
\t\t\t\t\t[
\t\t\t\t\t]
\t\t\t\t\t"dataTypes" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t]
\t\t\t\t\t"plugTypes" "int_array" 
\t\t\t\t\t[
\t\t\t\t\t]
\t\t\t\t\t"descriptions" "string_array" 
\t\t\t\t\t[
\t\t\t\t\t]
\t\t\t\t}}
\t\t\t\t"connectionsData" "element_array" 
\t\t\t\t[
\t\t\t\t]
\t\t\t\t"entity_properties" "EditGameClassProps"
\t\t\t\t{{
\t\t\t\t\t"id" "elementid" "{self.generate_uuid()}"
{chr(10).join(prop_strings)}
\t\t\t\t}}
\t\t\t\t"hitNormal" "vector3" "0 0 1"
\t\t\t\t"isProceduralEntity" "bool" "0"
\t\t\t\t"origin" "vector3" "{ox} {oy} {oz}"
\t\t\t\t"angles" "qangle" "0 0 0"
\t\t\t\t"scales" "vector3" "1 1 1"
\t\t\t\t"transformLocked" "bool" "0"
\t\t\t\t"force_hidden" "bool" "0"
\t\t\t\t"editorOnly" "bool" "0"
\t\t\t}}'''
        
        return entity
    
    def generate_vmap(self, level_data: Dict) -> str:
        """Generate complete VMAP file from simplified level description"""
        self.node_counter = 1
        
        meshes = []
        for room in level_data.get("rooms", []):
            mesh = self.create_box_mesh(
                room.get("width", 512),
                room.get("depth", 512),
                room.get("height", 256),
                tuple(room.get("origin", [0, 0, 0])),
                room.get("material", "materials/dev/reflectivity_30.vmat"),
                room.get("uv_scale", 128.0)
            )
            meshes.append(mesh)
        
        entities = []
        for ent in level_data.get("entities", []):
            entity = self.create_entity(
                ent["classname"],
                tuple(ent["origin"]),
                ent.get("properties"),
                tuple(ent.get("angles", (0, 0, 0)))
            )
            entities.append(entity)
        
        # Handle brush entities (like func_bomb_target)
        for brush_ent in level_data.get("brush_entities", []):
            entity = self.create_brush_entity(
                brush_ent["classname"],
                tuple(brush_ent["origin"]),
                brush_ent["width"],
                brush_ent["depth"],
                brush_ent["height"],
                brush_ent.get("properties"),
                brush_ent.get("material", "materials/tools/toolstrigger.vmat")
            )
            entities.append(entity)
        
        all_children = ",\n".join(meshes + entities)
        skyname = level_data.get("skyname", "sky_day01_01")
        
        vmap = f'''<!-- dmx encoding keyvalues2 4 format vmap 40 -->
"CMapRootElement"
{{
\t"id" "elementid" "{self.generate_uuid()}"
\t"isprefab" "bool" "0"
\t"editorbuild" "int" "10620"
\t"editorversion" "int" "400"
\t"itemFile" "string" ""
\t"defaultcamera" "CStoredCamera"
\t{{
\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t"position" "vector3" "0 -500 400"
\t\t"lookat" "vector3" "0 0 0"
\t}}
\t"3dcameras" "CStoredCameras"
\t{{
\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t"activecamera" "int" "-1"
\t\t"cameras" "element_array" 
\t\t[
\t\t]
\t}}
\t"world" "CMapWorld"
\t{{
\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t"nodeID" "int" "1"
\t\t"referenceID" "uint64" "0x0"
\t\t"children" "element_array" 
\t\t[
{all_children}
\t\t]
\t\t"variableTargetKeys" "string_array" 
\t\t[
\t\t]
\t\t"variableNames" "string_array" 
\t\t[
\t\t]
\t\t"relayPlugData" "DmePlugList"
\t\t{{
\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t"names" "string_array" 
\t\t\t[
\t\t\t]
\t\t\t"dataTypes" "int_array" 
\t\t\t[
\t\t\t]
\t\t\t"plugTypes" "int_array" 
\t\t\t[
\t\t\t]
\t\t\t"descriptions" "string_array" 
\t\t\t[
\t\t\t]
\t\t}}
\t\t"connectionsData" "element_array" 
\t\t[
\t\t]
\t\t"entity_properties" "EditGameClassProps"
\t\t{{
\t\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t\t"classname" "string" "worldspawn"
\t\t\t"targetname" "string" ""
\t\t\t"skyname" "string" "{skyname}"
\t\t\t"startdark" "string" "0"
\t\t\t"pvstype" "string" "10"
\t\t}}
\t\t"nextDecalID" "int" "0"
\t\t"fixupEntityNames" "bool" "1"
\t\t"mapUsageType" "string" "standard"
\t\t"origin" "vector3" "0 0 0"
\t\t"angles" "qangle" "0 0 0"
\t\t"scales" "vector3" "1 1 1"
\t}}
\t"visbility" "CVisibilityMgr"
\t{{
\t\t"id" "elementid" "{self.generate_uuid()}"
\t\t"nodeID" "int" "0"
\t}}
\t"mapVariables" "CMapVariableSet"
\t{{
\t\t"id" "elementid" "{self.generate_uuid()}"
\t}}
\t"rootSelectionSet" "CMapSelectionSet"
\t{{
\t\t"id" "elementid" "{self.generate_uuid()}"
\t}}
}}
'''
        return vmap


def grid_to_level_data(grid_level: Dict,
                       cell_size: float = 64.0,
                       cell_height: float = 64.0,
                       add_frame: bool = True,
                       add_floor: bool = True,
                       height_variation: bool = True,
                       default_material: str = "materials/dev/reflectivity_30.vmat",
                       floor_material: str = "materials/cs_italy/ground/cobblestone_ground_large_1.vmat",
                       cover_material: str = "materials/cs_italy/picrate1.vmat",
                       default_skyname: str = "sky_day01_01") -> Dict:
    """
    Convert a grid-based JSON description into the internal level_data format
    expected by VMAPGenerator.generate_vmap().
    """
    import random
    
    wall_materials = [
        "materials/brick/01/brick_clean_02.vmat",
        "materials/de_anubis/mudbrick02_plaster01_blend.vmat",
        "materials/concrete/hr_c/hr_concrete_wall_painted_003.vmat"
    ]
    
    grid = grid_level.get("grid")
    if not grid:
        raise ValueError("JSON must contain a 'grid' 2D array")

    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0

    width_cells = int(grid_level.get("width", cols))
    height_cells = int(grid_level.get("height", rows))

    frame_offset = 1 if add_frame else 0
    total_width_cells = width_cells + (frame_offset * 2)
    total_height_cells = height_cells + (frame_offset * 2)

    total_width = total_width_cells * cell_size
    total_height = total_height_cells * cell_size
    half_w = total_width / 2.0
    half_h = total_height / 2.0

    rooms = []
    
    cluster_data = {}
    if height_variation:
        cluster_size_min = 3
        cluster_size_max = 8
        height_min = 2
        height_max = 6
        
        x = 0
        while x < total_width_cells:
            cluster_w = random.randint(cluster_size_min, cluster_size_max)
            y = 0
            while y < total_height_cells:
                cluster_h = random.randint(cluster_size_min, cluster_size_max)
                cluster_height_mult = random.randint(height_min, height_max)
                cluster_material = random.choice(wall_materials)
                
                for cx in range(x, min(x + cluster_w, total_width_cells)):
                    for cy in range(y, min(y + cluster_h, total_height_cells)):
                        cluster_data[(cx, cy)] = (cluster_height_mult, cluster_material)
                
                y += cluster_h
            x += cluster_w

    def add_block(x_idx, y_idx, material=default_material, force_height=None, uv_scale=128.0):
        world_x = -half_w + x_idx * cell_size + cell_size / 2.0
        world_y = -half_h + y_idx * cell_size + cell_size / 2.0
        
        if force_height is not None:
            height_mult = force_height
            block_material = material
        elif height_variation and (x_idx, y_idx) in cluster_data:
            height_mult, block_material = cluster_data[(x_idx, y_idx)]
        else:
            height_mult = 2
            block_material = material
        
        block_height = cell_height * height_mult
        world_z = block_height / 2.0

        rooms.append({
            "width": cell_size,
            "depth": cell_size,
            "height": block_height,
            "origin": [world_x, world_y, world_z],
            "material": block_material,
            "uv_scale": uv_scale
        })

    if add_frame:
        for x in range(total_width_cells):
            for y in range(total_height_cells):
                is_top = (y == 0)
                is_bottom = (y == total_height_cells - 1)
                is_left = (x == 0)
                is_right = (x == total_width_cells - 1)
                
                if is_top or is_bottom or is_left or is_right:
                    add_block(x, y)

    if add_floor:
        floor_height = cell_height
        rooms.append({
            "width": total_width,
            "depth": total_height,
            "height": floor_height,
            "origin": [0, 0, -floor_height / 2.0],
            "material": floor_material
        })

    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value == 0:
                grid_x = x + frame_offset
                grid_y = y + frame_offset
                add_block(grid_x, grid_y)
            elif value == 9:
                # Cover objects - low height crates with smaller UV scale
                grid_x = x + frame_offset
                grid_y = y + frame_offset
                # Random height of 1 or 2 cell heights for variety
                cover_height = random.choice([1, 2])
                add_block(grid_x, grid_y, material=cover_material, force_height=cover_height, uv_scale=64.0)

    level_data = {
        "skyname": default_skyname,
        "rooms": rooms,
        "entities": [],
        "brush_entities": []
    }

    areas = grid_level.get("areas", {})
    for area_name, area_data in areas.items():
        if area_data.get("name") in ["A", "B"]:
            site_x = area_data.get("x", 0)
            site_y = area_data.get("y", 0)
            site_w = area_data.get("w", 4)
            site_h = area_data.get("h", 4)
            site_name = area_data.get("name", "A")
            
            grid_center_x = site_x + site_w / 2.0 + frame_offset
            grid_center_y = site_y + site_h / 2.0 + frame_offset
            
            world_x = -half_w + grid_center_x * cell_size
            world_y = -half_h + grid_center_y * cell_size
            world_z = cell_height
            
            trigger_width = site_w * cell_size
            trigger_depth = site_h * cell_size
            trigger_height = cell_height * 2
            
            site_designation = "0" if site_name == "A" else "1"
            
            level_data["brush_entities"].append({
                "classname": "func_bomb_target",
                "origin": [world_x, world_y, world_z],
                "width": trigger_width,
                "depth": trigger_depth,
                "height": trigger_height,
                "properties": {
                    "targetname": f"bombsite_{site_name.lower()}",
                    "heistbomb": "0",
                    "bomb_mount_target": "",
                    "bomb_site_designation": site_designation
                }
            })

    t_spawn_cells = []
    ct_spawn_cells = []
    
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value == 3:
                t_spawn_cells.append((x, y))
            elif value == 4:
                ct_spawn_cells.append((x, y))
    
    def get_spawn_position(cells):
        if not cells:
            return None
        mid_idx = len(cells) // 2
        x, y = cells[mid_idx]
        
        grid_x = x + frame_offset
        grid_y = y + frame_offset
        
        world_x = -half_w + grid_x * cell_size + cell_size / 2.0
        world_y = -half_h + grid_y * cell_size + cell_size / 2.0
        
        return [world_x, world_y, 1.0]
    
    t_spawn_pos = get_spawn_position(t_spawn_cells)
    ct_spawn_pos = get_spawn_position(ct_spawn_cells)
    
    if t_spawn_pos:
        level_data["entities"].append({
            "classname": "info_player_terrorist",
            "origin": t_spawn_pos,
            "angles": (0, 0, 0),
            "properties": {
                "targetname": "",
                "priority": "0",
                "enabled": "1"
            }
        })
    
    if ct_spawn_pos:
        level_data["entities"].append({
            "classname": "info_player_counterterrorist",
            "origin": ct_spawn_pos,
            "angles": (0, 0, 0),
            "properties": {
                "targetname": "",
                "priority": "0",
                "enabled": "1"
            }
        })
    
    level_data["entities"].append({
        "classname": "light_environment",
        "origin": [0, 0, 500],
        "angles": (45, 45, 0),
        "properties": {
            "targetname": "",
            "color": "255 255 255",
            "brightness": "1.0",
            "castshadows": "1",
            "skycolor": "255 255 255",
            "skyintensity": "1.0",
            "angulardiameter": "1.0"
        }
    })
    
    level_data["entities"].append({
        "classname": "env_sky",
        "origin": [0, 0, 64],
        "angles": (0, 0, 0),
        "properties": {
            "targetname": "",
            "StartDisabled": "0",
            "skyname": "materials/dev/default_sky.vmat",
            "tint_color": "255 255 255",
            "brightnessscale": "1.0"
        }
    })

    return level_data


class VMAPGeneratorGUI:
    """GUI for VMAP Generator (grid-based JSON)"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("CS2 VMAP Level Generator (Grid JSON)")
        self.root.geometry("700x400")
        
        self.generator = VMAPGenerator()
        self.config = self.load_config()
        self.create_widgets()
        
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "json_path": DEFAULT_JSON_PATH,
            "output_path": DEFAULT_CS2_PATH
        }
    
    def save_config(self):
        config = {
            "json_path": self.json_path_var.get(),
            "output_path": self.output_path_var.get()
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    
    def create_widgets(self):
        title = tk.Label(self.root, text="CS2 VMAP Level Generator (Grid → Boxes)", 
                        font=("Arial", 16, "bold"))
        title.pack(pady=10)
        
        main_frame = tk.Frame(self.root, padx=20, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        json_frame = tk.LabelFrame(main_frame, text="Input JSON Level File (grid-based)", padx=10, pady=10)
        json_frame.pack(fill=tk.X, pady=5)
        
        self.json_path_var = tk.StringVar(value=self.config.get("json_path", ""))
        
        json_entry_frame = tk.Frame(json_frame)
        json_entry_frame.pack(fill=tk.X)
        
        tk.Entry(json_entry_frame, textvariable=self.json_path_var, width=60).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        tk.Button(json_entry_frame, text="Browse...", command=self.browse_json).pack(side=tk.LEFT, padx=2)
        tk.Button(json_entry_frame, text="Set Default", command=self.set_json_default).pack(side=tk.LEFT)
        
        output_frame = tk.LabelFrame(main_frame, text="Output VMAP Folder", padx=10, pady=10)
        output_frame.pack(fill=tk.X, pady=5)
        
        self.output_path_var = tk.StringVar(value=self.config.get("output_path", DEFAULT_CS2_PATH))
        
        output_entry_frame = tk.Frame(output_frame)
        output_entry_frame.pack(fill=tk.X)
        
        tk.Entry(output_entry_frame, textvariable=self.output_path_var, width=60).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        tk.Button(output_entry_frame, text="Browse...", command=self.browse_output).pack(side=tk.LEFT, padx=2)
        tk.Button(output_entry_frame, text="Set Default", command=self.set_output_default).pack(side=tk.LEFT)
        
        options_frame = tk.LabelFrame(main_frame, text="Options", padx=10, pady=10)
        options_frame.pack(fill=tk.X, pady=5)
        
        self.add_frame_var = tk.BooleanVar(value=True)
        tk.Checkbutton(options_frame, text="Add frame (outer wall) around map", 
                      variable=self.add_frame_var).pack(anchor=tk.W)
        
        self.add_floor_var = tk.BooleanVar(value=True)
        tk.Checkbutton(options_frame, text="Add floor under map", 
                      variable=self.add_floor_var).pack(anchor=tk.W)
        
        self.height_variation_var = tk.BooleanVar(value=True)
        tk.Checkbutton(options_frame, text="Height variation (building-like walls)", 
                      variable=self.height_variation_var).pack(anchor=tk.W)
        
        info_frame = tk.LabelFrame(main_frame, text="Grid JSON Format Info", padx=10, pady=10)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        info_text = tk.Text(info_frame, height=6, wrap=tk.WORD, font=("Courier", 9))
        info_text.pack(fill=tk.BOTH, expand=True)
        info_text.insert("1.0", '''Cell value 0 = solid block (wall)
Cell values 1-9 = open space (walkable)

Options:
- "Add frame" adds an outer boundary wall around all four sides
- "Add floor" places floor blocks under the entire map to walk on
- "Height variation" groups walls into clusters with random heights and materials''')
        info_text.config(state=tk.DISABLED)
        
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=10)
        
        self.generate_btn = tk.Button(button_frame, text="Generate VMAP Level", 
                                      command=self.generate_level,
                                      bg="#4CAF50", fg="white", 
                                      font=("Arial", 12, "bold"),
                                      padx=20, pady=10)
        self.generate_btn.pack()
        
        self.status_var = tk.StringVar(value="Ready")
        status_label = tk.Label(main_frame, textvariable=self.status_var, 
                               font=("Arial", 10), fg="blue")
        status_label.pack(pady=5)
    
    def browse_json(self):
        filename = filedialog.askopenfilename(
            title="Select JSON Level File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.json_path_var.set(filename)
    
    def browse_output(self):
        folder = filedialog.askdirectory(
            title="Select Output Folder for VMAP Files",
            initialdir=self.output_path_var.get()
        )
        if folder:
            self.output_path_var.set(folder)
    
    def set_json_default(self):
        self.save_config()
        messagebox.showinfo("Success", "JSON path saved as default!")
    
    def set_output_default(self):
        self.save_config()
        messagebox.showinfo("Success", "Output path saved as default!")
    
    def generate_level(self):
        json_path = self.json_path_var.get()
        output_path = self.output_path_var.get()
        
        if not json_path or not os.path.exists(json_path):
            messagebox.showerror("Error", "Please select a valid JSON input file!")
            return
        
        if not output_path:
            messagebox.showerror("Error", "Please specify an output folder!")
            return
        
        try:
            os.makedirs(output_path, exist_ok=True)
            
            self.status_var.set("Loading JSON...")
            self.root.update()
            
            with open(json_path, 'r') as f:
                grid_level = json.load(f)
            
            self.status_var.set("Converting grid to level data...")
            self.root.update()

            level_data = grid_to_level_data(
                grid_level,
                add_frame=self.add_frame_var.get(),
                add_floor=self.add_floor_var.get(),
                height_variation=self.height_variation_var.get()
            )
            
            self.status_var.set("Generating VMAP...")
            self.root.update()
            
            vmap_content = self.generator.generate_vmap(level_data)
            
            json_filename = os.path.basename(json_path)
            vmap_filename = os.path.splitext(json_filename)[0] + ".vmap"
            output_file = os.path.join(output_path, vmap_filename)
            
            self.status_var.set("Saving VMAP file...")
            self.root.update()
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(vmap_content)
            
            num_blocks = len(level_data["rooms"])
            self.status_var.set(f"✓ Successfully generated: {vmap_filename} ({num_blocks} blocks)")
            messagebox.showinfo("Success", 
                              f"VMAP file generated successfully!\n\n"
                              f"Location: {output_file}\n"
                              f"Total blocks: {num_blocks}\n\n"
                              f"Next steps:\n"
                              f"1. Open CS2 Workshop Tools\n"
                              f"2. Tools → Hammer\n"
                              f"3. File → Open → {vmap_filename}\n"
                              f"4. Map → Build Map")
            
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON Error", f"Invalid JSON file:\n{str(e)}")
            self.status_var.set("Error: Invalid JSON")
        except Exception as e:
            messagebox.showerror("Error", f"Generation failed:\n{str(e)}")
            self.status_var.set("Error during generation")


def create_example_json():
    example = {
        "width": 8,
        "height": 8,
        "grid": [
            [0, 0, 1, 1, 0, 0, 0, 0],
            [0, 1, 1, 1, 0, 2, 2, 0],
            [0, 1, 0, 0, 0, 2, 2, 0],
            [0, 1, 0, 9, 0, 2, 2, 0],
            [0, 1, 0, 0, 0, 2, 2, 0],
            [0, 1, 1, 1, 0, 2, 2, 0],
            [0, 0, 0, 0, 0, 2, 2, 0],
            [0, 0, 0, 0, 0, 0, 0, 0]
        ]
    }
    
    with open("example_grid_level.json", "w") as f:
        json.dump(example, f, indent=2)
    
    print("✓ Created example_grid_level.json")


if __name__ == "__main__":
    if not os.path.exists("example_grid_level.json"):
        create_example_json()
    
    root = tk.Tk()
    app = VMAPGeneratorGUI(root)
    root.mainloop()