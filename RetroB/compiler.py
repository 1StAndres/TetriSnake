# compiler.py
# Compilador universal para BrickScript (Version Extendida - Accesibilidad)
# Uso: python3 compiler.py <archivo_entrada.brick>

import sys
import re
import json


def lexer(codigo_fuente):
    # OJO: antes se eliminaban comentarios con '#.*' completo. Como ahora
    # '#RRGGBB' tambien empieza con '#', hay que evitar borrar los colores.
    # Solo se trata como comentario un '#' que NO sea seguido de 6 digitos
    # hexadecimales exactos (que es la forma de un color valido).
    codigo_fuente = re.sub(r'#(?![0-9A-F]{6}\b).*', '', codigo_fuente)

    # Orden importa: primero los tokens mas "especificos" (cadenas, colores,
    # decimales), despues numeros enteros, palabras clave/identificadores y
    # finalmente signos de puntuacion.
    token_regex = (
        r'"[^"]*"'          # cadenas de texto "..."
        r'|#[0-9A-F]{6}\b'  # colores hexadecimales #RRGGBB
        r'|\d+\.\d+'        # decimales (ej. TICK_MULTIPLIER : 1.5)
        r'|\d+'             # enteros
        r'|\b[A-Z_]+\b'     # palabras clave / identificadores
        r'|[\[\](),:]'      # puntuacion
    )
    tokens = re.findall(token_regex, codigo_fuente)
    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.posicion = 0
        self.ast = {
            "tipo_juego": None,
            "config": {},
            "shapes": {},
            "fruits": {},        # NUEVO
            "stage_colors": [],  # NUEVO
            "events": {},
        }

    def parse(self):
        while self.posicion < len(self.tokens):
            token_actual = self.tokens[self.posicion]
            if token_actual == 'GAME_TYPE':
                self.parsear_tipo_juego()
            elif token_actual == 'GAME_GRID':
                self.parsear_grid()
            elif token_actual in ('TICK_MULTIPLIER', 'STREAK_TARGET'):
                self.parsear_config()
            elif token_actual == 'DEFINE':
                self.parsear_definicion()
            elif token_actual == 'ON':
                self.parsear_evento()
            else:
                self.posicion += 1
        return self.ast

    def consumir(self, token_esperado=None):
        if self.posicion < len(self.tokens):
            token = self.tokens[self.posicion]
            if token_esperado and token != token_esperado:
                raise Exception(
                    "Error de sintaxis: Se esperaba '" + token_esperado +
                    "' pero se encontro '" + token + "'"
                )
            self.posicion += 1
            return token
        if token_esperado:
            raise Exception(
                "Error de sintaxis: Se esperaba '" + token_esperado +
                "' pero se llego al final del archivo."
            )
        return None

    def ver_siguiente(self, offset=1):
        pos = self.posicion + offset
        if pos < len(self.tokens):
            return self.tokens[pos]
        return None

    def parsear_tipo_juego(self):
        self.consumir('GAME_TYPE')
        self.ast['tipo_juego'] = self.consumir()

    def parsear_grid(self):
        self.consumir('GAME_GRID')
        self.consumir('(')
        ancho = int(self.consumir())
        self.consumir(',')
        alto = int(self.consumir())
        self.consumir(')')
        self.ast['config']['grid_size'] = [ancho, alto]

    # --- NUEVO: bloque de configuracion global opcional ---
    def parsear_config(self):
        token = self.tokens[self.posicion]
        if token == 'TICK_MULTIPLIER':
            self.consumir('TICK_MULTIPLIER')
            self.consumir(':')
            self.ast['config']['tick_multiplier'] = float(self.consumir())
        elif token == 'STREAK_TARGET':
            self.consumir('STREAK_TARGET')
            self.consumir(':')
            self.ast['config']['streak_target'] = int(self.consumir())

    # --- NUEVO: dispatcher para DEFINE, ya que ahora puede ser
    # SHAPE, FRUIT o STAGE_COLORS ---
    def parsear_definicion(self):
        siguiente = self.ver_siguiente()
        if siguiente == 'SHAPE':
            self.parsear_shape()
        elif siguiente == 'FRUIT':
            self.parsear_fruit()
        elif siguiente == 'STAGE_COLORS':
            self.parsear_stage_colors()
        else:
            raise Exception(
                "Error de sintaxis: DEFINE desconocido, se encontro '" +
                str(siguiente) + "'"
            )

    def parsear_shape(self):
        self.consumir('DEFINE')
        self.consumir('SHAPE')
        nombre_shape = self.consumir()
        self.consumir(':')
        estados = []
        while self.posicion < len(self.tokens) and self.tokens[self.posicion] == 'STATE':
            self.consumir('STATE')
            self.consumir()
            self.consumir(':')
            matriz = []
            while self.posicion < len(self.tokens) and self.tokens[self.posicion] == '[':
                fila = []
                self.consumir('[')
                while self.tokens[self.posicion] != ']':
                    fila.append(int(self.consumir()))
                    if self.tokens[self.posicion] == ',':
                        self.consumir(',')
                self.consumir(']')
                matriz.append(fila)
            estados.append(matriz)
        self.consumir('END')
        self.ast['shapes'][nombre_shape] = estados

    # --- NUEVO: DEFINE FRUIT ---
    def parsear_fruit(self):
        self.consumir('DEFINE')
        self.consumir('FRUIT')
        nombre_fruit = self.consumir()
        self.consumir(':')
        atributos = {}
        while self.posicion < len(self.tokens) and self.tokens[self.posicion] != 'END':
            attr = self.tokens[self.posicion]
            if attr == 'COLOR':
                self.consumir('COLOR')
                self.consumir(':')
                atributos['color'] = self.consumir()
            elif attr == 'SCORE':
                self.consumir('SCORE')
                self.consumir(':')
                atributos['score'] = int(self.consumir())
            elif attr == 'PATTERN':
                self.consumir('PATTERN')
                self.consumir(':')
                atributos['pattern'] = self.consumir()
            elif attr == 'EFFECT':
                self.consumir('EFFECT')
                self.consumir(':')
                atributos['effect'] = self.consumir()
            elif attr == 'LIFETIME':
                self.consumir('LIFETIME')
                self.consumir(':')
                atributos['lifetime'] = int(self.consumir())
            else:
                raise Exception(
                    "Error de sintaxis: atributo de FRUIT desconocido '" + attr + "'"
                )
        self.consumir('END')
        self.ast['fruits'][nombre_fruit] = atributos

    # --- NUEVO: DEFINE STAGE_COLORS ---
    def parsear_stage_colors(self):
        self.consumir('DEFINE')
        self.consumir('STAGE_COLORS')
        self.consumir(':')
        stages = []
        while self.posicion < len(self.tokens) and self.tokens[self.posicion] == 'STAGE':
            self.consumir('STAGE')
            self.consumir('(')
            minimo = int(self.consumir())
            self.consumir(',')
            maximo = int(self.consumir())
            self.consumir(')')
            self.consumir(':')
            color = self.consumir()
            stages.append({'rango': [minimo, maximo], 'color': color})
        self.consumir('END')
        self.ast['stage_colors'] = stages

    def parsear_evento(self):
        self.consumir('ON')
        nombre_evento = 'ON_' + self.consumir()
        self.consumir(':')
        acciones = []

        # Palabras clave que NO deben interpretarse como un parametro suelto
        # de la accion anterior (usado mas abajo para saber donde parar).
        palabras_clave_accion = [
            'END', 'ON', 'DEFINE', 'SPAWN', 'MOVE', 'ROTATE',
            'INCREASE_SCORE', 'SET_DIRECTION', 'GROW', 'GAME_OVER',
            'TOGGLE_PAUSE', 'TOGGLE_MUTE', 'PLAY_SOUND',
        ]

        while self.posicion < len(self.tokens) and self.tokens[self.posicion] != 'END':
            verbo = self.consumir()

            # --- Comandos de una sola palabra (sin objeto) ---
            if verbo in ('GAME_OVER', 'TOGGLE_PAUSE', 'TOGGLE_MUTE'):
                acciones.append({'accion': verbo, 'objeto': None, 'params': []})
                continue

            # --- NUEVO: PLAY_SOUND "archivo.wav" ---
            if verbo == 'PLAY_SOUND':
                cadena = self.consumir()
                texto = cadena.strip('"')
                acciones.append({'accion': verbo, 'objeto': None, 'params': [texto]})
                continue

            # --- Resto de acciones existentes (con objeto) ---
            objeto = self.consumir()
            params = []
            if self.posicion < len(self.tokens) and self.tokens[self.posicion] == 'AT':
                self.consumir('AT')
                if self.tokens[self.posicion] == 'RANDOM':
                    params.append(self.consumir())
                else:
                    self.consumir('(')
                    x = int(self.consumir())
                    self.consumir(',')
                    y = int(self.consumir())
                    self.consumir(')')
                    params.append([x, y])
            elif (self.posicion < len(self.tokens)
                    and self.tokens[self.posicion] not in palabras_clave_accion):
                params.append(self.consumir())
            acciones.append({'accion': verbo, 'objeto': objeto, 'params': params})
        self.consumir('END')
        self.ast['events'][nombre_evento] = acciones


def generar_codigo(ast, archivo_salida):
    with open(archivo_salida, 'w') as f:
        json.dump(ast, f, indent=2)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 compiler.py <archivo_entrada.brick>")
        sys.exit(1)
    archivo_entrada = sys.argv[1]
    archivo_salida = archivo_entrada.replace('.brick', '.json')
    print("Compilando " + archivo_entrada + "...")
    try:
        with open(archivo_entrada, 'r') as f:
            codigo = f.read()
        tokens = lexer(codigo)
        parser = Parser(tokens)
        ast = parser.parse()
        generar_codigo(ast, archivo_salida)
        print("Compilacion exitosa! Archivo de juego creado en " + archivo_salida)
    except Exception as e:
        print("\n!!! ERROR DE COMPILACION !!!")
        print(str(e))
        sys.exit(1)