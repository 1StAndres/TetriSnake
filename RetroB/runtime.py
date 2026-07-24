# -*- coding: utf-8 -*-
# runtime.py (VERSION EXTENDIDA - GUI Tkinter + Accesibilidad para Snake)
# Uso: python3 runtime.py <archivo_juego.json>

import sys
import json
import random

import tkinter as tk
from tkinter import messagebox

# El modulo winsound solo existe en Windows. Se protege el import para que
# el runtime no se caiga si alguien lo prueba en otro sistema operativo;
# simplemente el audio quedara deshabilitado.
try:
    import winsound
    AUDIO_DISPONIBLE = True
except ImportError:
    AUDIO_DISPONIBLE = False

# Colores por defecto si el .brick NO define STAGE_COLORS ni FRUIT
# (garantiza que snake.brick original siga funcionando igual que antes)
COLOR_SNAKE_CABEZA_DEFECTO = '#00FF00'
COLOR_SNAKE_CUERPO_DEFECTO = '#33CC33'
COLOR_FOOD_DEFECTO = '#FF0000'


class Juego:
    def __init__(self, datos_juego):
        self.datos_juego = datos_juego
        self.tipo_juego = self.datos_juego.get('tipo_juego', 'TETRIS')
        config = self.datos_juego.get('config', {})
        self.ancho = config.get('grid_size', [10, 20])[0]
        self.alto = config.get('grid_size', [10, 20])[1]
        self.grid = [[0 for _ in range(self.ancho)] for _ in range(self.alto)]
        self.puntuacion = 0
        self.juego_terminado = False

        # --- NUEVO: estado de accesibilidad (S08 Silenciar, S09 Pausa) ---
        # Generico: funciona sin importar el tipo de juego (Tetris o Snake)
        self.pausado = False
        self.silenciado = False

        # --- Configuracion de la GUI ---
        self.root = tk.Tk()
        self.root.title("BrickScript - " + self.tipo_juego)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar_ventana)

        self.taman_celda = 25
        self.ancho_canvas = self.ancho * self.taman_celda
        self.alto_canvas = self.alto * self.taman_celda

        self.canvas = tk.Canvas(self.root, width=self.ancho_canvas, height=self.alto_canvas, bg='#111111')
        self.canvas.pack(side=tk.LEFT, padx=10, pady=10)

        self.marco_score = tk.Frame(self.root, width=190, height=self.alto_canvas, bg='#222222')
        self.marco_score.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        self.label_score = tk.Label(self.marco_score, text="PUNTUACION\n0", bg='#222222', fg='white',
                                     font=('Consolas', 16, 'bold'))
        self.label_score.pack(pady=(30, 10), padx=10)

        # NUEVO S07: racha
        self.label_racha = tk.Label(self.marco_score, text="RACHA\n0", bg='#222222', fg='#FFD700',
                                     font=('Consolas', 12, 'bold'))
        self.label_racha.pack(pady=10, padx=10)

        # NUEVO S03: contador de frutas consumidas por tipo
        self.label_frutas = tk.Label(self.marco_score, text="", bg='#222222', fg='#AAAAAA',
                                      font=('Consolas', 9), justify=tk.LEFT)
        self.label_frutas.pack(pady=10, padx=10)

        # NUEVO: indicador de estado (silencio / efecto activo)
        self.label_estado = tk.Label(self.marco_score, text="", bg='#222222', fg='#FF6666',
                                      font=('Consolas', 10, 'bold'))
        self.label_estado.pack(pady=10, padx=10)

        self.label_controles = tk.Label(
            self.marco_score,
            text="CONTROLES\nFlechas: Mover\nP: Pausa\nM: Silenciar",
            bg='#222222', fg='gray', font=('Consolas', 10)
        )
        self.label_controles.pack(pady=20, padx=10)

        self.root.bind('<Key>', self.manejar_input_gui)

        if self.tipo_juego == 'TETRIS':
            self.pieza_actual = None
            self.pieza_x, self.pieza_y, self.pieza_rotacion = 0, 0, 0
            self.velocidad_gravedad = 0.4

        if self.tipo_juego == 'SNAKE':
            self.serpiente_cuerpo = []
            self.serpiente_direccion = (1, 0)
            self.posicion_comida = None

            # NUEVO S04-S06: tipos de fruta. Si el .brick no define ninguna
            # fruta con DEFINE FRUIT, se usa una fruta generica de 1 punto
            # para que snake.brick original siga funcionando igual.
            self.frutas_definidas = self.datos_juego.get('fruits', {})
            if not self.frutas_definidas:
                self.frutas_definidas = {
                    'DEFAULT': {'color': COLOR_FOOD_DEFECTO, 'score': 1, 'pattern': 'SOLID', 'effect': 'NONE'}
                }
            self.fruta_actual = None
            self.contador_frutas = {}  # NUEVO S03

            # NUEVO S07: racha
            self.racha_actual = 0
            self.streak_target = config.get('streak_target', 5)

            # NUEVO S01: colores de la serpiente segun etapa (tamano del cuerpo)
            self.stage_colors = self.datos_juego.get('stage_colors', [])

            # NUEVO: efecto temporal activado por frutas especiales (EFFECT)
            self.efecto_activo = None
            self.efecto_ticks_restantes = 0

            self.velocidad_gravedad = 0.15

        # NUEVO: TICK_MULTIPLIER opcional (config global del .brick)
        self.velocidad_base = self.velocidad_gravedad
        self.velocidad_gravedad *= config.get('tick_multiplier', 1.0)

        self.timer_gravedad = 0
        self.ejecutar_evento('ON_START')
        self.timer_id = None

    def run(self):
        self.root.after(50, self.game_loop)
        self.root.mainloop()

    def game_loop(self):
        if self.juego_terminado:
            self.mostrar_game_over()
            return

        # NUEVO S09: si esta en pausa no se procesa logica de juego,
        # pero se sigue dibujando para mostrar el overlay de "PAUSA"
        if not self.pausado:
            self.timer_gravedad += 0.05
            if self.timer_gravedad >= self.velocidad_gravedad:
                self.timer_gravedad = 0
                self.ejecutar_evento('ON_TICK')
                self._actualizar_efecto_temporal()

        self.dibujar()
        self.timer_id = self.root.after(50, self.game_loop)

    def cerrar_ventana(self):
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
        self.root.destroy()
        sys.exit(0)

    def manejar_input_gui(self, event):
        key = event.keysym.upper()

        # NUEVO S09 / S08: pausa y silencio son controles globales de
        # accesibilidad, funcionan siempre, sin depender del .brick
        if key == 'P':
            self.snake_toggle_pausa()
            return
        if key == 'M':
            self.snake_toggle_mute()
            return

        if self.pausado:
            return  # mientras esta en pausa se ignoran las demas teclas

        if self.tipo_juego == 'TETRIS':
            if key == 'UP': self.ejecutar_evento('ON_KEY_UP')
            elif key == 'DOWN': self.ejecutar_evento('ON_KEY_DOWN')
            elif key == 'LEFT': self.ejecutar_evento('ON_KEY_LEFT')
            elif key == 'RIGHT': self.ejecutar_evento('ON_KEY_RIGHT')
        elif self.tipo_juego == 'SNAKE':
            if key == 'UP': self.snake_cambiar_direccion('UP')
            elif key == 'DOWN': self.snake_cambiar_direccion('DOWN')
            elif key == 'LEFT': self.snake_cambiar_direccion('LEFT')
            elif key == 'RIGHT': self.snake_cambiar_direccion('RIGHT')

    # ------------------------------------------------------------------
    # DIBUJO
    # ------------------------------------------------------------------

    def dibujar(self):
        self.canvas.delete("all")
        self.label_score.config(text="PUNTUACION\n" + str(self.puntuacion))

        COLOR_GRID_FIJA = '#343434'
        COLOR_PIEZA = '#00FFFF'

        for y in range(self.alto):
            for x in range(self.ancho):
                if self.grid[y][x] == 1:
                    self.dibujar_celda(x, y, COLOR_GRID_FIJA)

        if self.tipo_juego == 'TETRIS' and self.pieza_actual:
            matriz_pieza = self.pieza_actual[self.pieza_rotacion]
            for y_offset, fila in enumerate(matriz_pieza):
                for x_offset, celda in enumerate(fila):
                    if celda == 1:
                        self.dibujar_celda(self.pieza_x + x_offset, self.pieza_y + y_offset, COLOR_PIEZA)

        if self.tipo_juego == 'SNAKE':
            self._dibujar_snake()
            self.label_racha.config(text="RACHA\n" + str(self.racha_actual))
            self.label_frutas.config(text=self._texto_contador_frutas())
            self.label_estado.config(text=self._texto_estado())

        if self.pausado:
            self._dibujar_overlay_pausa()

    def _dibujar_snake(self):
        # S04-S06: la comida se dibuja con el color y el patron de su tipo de fruta
        if self.posicion_comida and self.fruta_actual:
            x, y = self.posicion_comida
            color = self.fruta_actual.get('color', COLOR_FOOD_DEFECTO)
            patron = self.fruta_actual.get('pattern', 'SOLID')
            self.dibujar_celda(x, y, color, patron)

        # S01: color de la serpiente segun la etapa actual (tamano del cuerpo)
        color_cabeza, color_cuerpo = self._colores_actuales_snake()
        for i, segmento in enumerate(self.serpiente_cuerpo):
            x, y = segmento
            color = color_cabeza if i == 0 else color_cuerpo
            # S02: puntos decorativos en el cuerpo (cada 3 segmentos)
            patron = 'DOTS' if i > 0 and i % 3 == 0 else None
            self.dibujar_celda(x, y, color, patron)

    def _colores_actuales_snake(self):
        """S01: determina el color de la serpiente segun su longitud actual."""
        longitud = len(self.serpiente_cuerpo)
        for etapa in self.stage_colors:
            minimo, maximo = etapa['rango']
            if minimo <= longitud <= maximo:
                color = etapa['color']
                return color, color
        # Retrocompatibilidad: si el .brick no trae STAGE_COLORS, colores clasicos
        return COLOR_SNAKE_CABEZA_DEFECTO, COLOR_SNAKE_CUERPO_DEFECTO

    def dibujar_celda(self, x, y, color, patron=None):
        ts = self.taman_celda
        x1, y1 = x * ts, y * ts
        x2, y2 = x1 + ts, y1 + ts
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline='#000000')

        # NUEVO: patrones dentro de la celda ademas del color (S02 / S06 /
        # rediseno visual). Ayuda tambien a usuarios con daltonismo, ya que
        # no dependen unicamente del color para distinguir elementos.
        if patron == 'STRIPES':
            for i in (1, 2):
                ly = y1 + (i * ts // 3)
                self.canvas.create_line(x1, ly, x2, ly, fill='#000000', width=1)
        elif patron == 'DOTS':
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            r = ts // 6
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill='#000000', outline='')

    def _dibujar_overlay_pausa(self):
        self.canvas.create_rectangle(0, 0, self.ancho_canvas, self.alto_canvas, fill='#000000', stipple='gray50')
        self.canvas.create_text(
            self.ancho_canvas // 2, self.alto_canvas // 2,
            text="PAUSA\n(presiona P para continuar)",
            fill='white', font=('Consolas', 14, 'bold'), justify=tk.CENTER
        )

    def _texto_contador_frutas(self):
        if not self.contador_frutas:
            return "FRUTAS\n(ninguna aun)"
        lineas = ["FRUTAS"]
        for nombre, cantidad in self.contador_frutas.items():
            lineas.append(nombre + ": " + str(cantidad))
        return "\n".join(lineas)

    def _texto_estado(self):
        estados = []
        if self.silenciado:
            estados.append("SONIDO: OFF")
        if self.efecto_activo:
            estados.append("EFECTO: " + self.efecto_activo)
        return "\n".join(estados)

    # ------------------------------------------------------------------
    # EVENTOS / ACCIONES DEL DSL
    # ------------------------------------------------------------------

    def ejecutar_evento(self, nombre_evento):
        if nombre_evento in self.datos_juego['events']:
            for accion in self.datos_juego['events'][nombre_evento]:
                verbo, objeto = accion.get('accion'), accion.get('objeto')

                if verbo == 'INCREASE_SCORE': self.puntuacion += int(objeto)
                if verbo == 'GAME_OVER': self.juego_terminado = True

                # NUEVO: acciones de accesibilidad, disponibles en cualquier
                # evento y cualquier tipo de juego (S08, S09, S10)
                if verbo == 'TOGGLE_PAUSE': self.snake_toggle_pausa()
                if verbo == 'TOGGLE_MUTE': self.snake_toggle_mute()
                if verbo == 'PLAY_SOUND': self.reproducir_sonido(accion['params'][0])

                if self.tipo_juego == 'TETRIS':
                    if verbo == 'SPAWN': self.tetris_spawn_pieza()
                    if verbo == 'MOVE': self.tetris_mover_pieza(accion['params'][0])
                    if verbo == 'ROTATE': self.tetris_rotar_pieza()

                if self.tipo_juego == 'SNAKE':
                    if verbo == 'SPAWN' and objeto == 'PLAYER': self.snake_spawn_jugador(accion)
                    if verbo == 'SPAWN' and objeto == 'FOOD': self.snake_spawn_comida()
                    if verbo == 'MOVE' and objeto == 'PLAYER': self.snake_mover_jugador()
                    if verbo == 'GROW': self.snake_crecer()

    # ------------------------------------------------------------------
    # TETRIS (logica identica a la version original, sin cambios)
    # ------------------------------------------------------------------

    def tetris_spawn_pieza(self):
        nombre_pieza = random.choice(list(self.datos_juego['shapes'].keys()))
        self.pieza_actual = self.datos_juego['shapes'][nombre_pieza]
        self.pieza_x, self.pieza_y, self.pieza_rotacion = self.ancho // 2 - 2, 0, 0
        if self.tetris_verificar_colision(self.pieza_x, self.pieza_y, self.pieza_rotacion):
            self.juego_terminado = True

    def tetris_mover_pieza(self, direccion):
        if not self.pieza_actual: return
        dx, dy = 0, 0
        if direccion == 'LEFT': dx = -1
        elif direccion == 'RIGHT': dx = 1
        elif direccion == 'DOWN': dy = 1
        if not self.tetris_verificar_colision(self.pieza_x + dx, self.pieza_y + dy, self.pieza_rotacion):
            self.pieza_x += dx
            self.pieza_y += dy
        elif dy > 0:
            self.tetris_fijar_pieza()

    def tetris_rotar_pieza(self):
        if not self.pieza_actual: return
        nueva_rotacion = (self.pieza_rotacion + 1) % len(self.pieza_actual)
        if not self.tetris_verificar_colision(self.pieza_x, self.pieza_y, nueva_rotacion):
            self.pieza_rotacion = nueva_rotacion

    def tetris_fijar_pieza(self):
        matriz_pieza = self.pieza_actual[self.pieza_rotacion]
        for y_offset, fila in enumerate(matriz_pieza):
            for x_offset, celda in enumerate(fila):
                if celda == 1:
                    if 0 <= self.pieza_y + y_offset < self.alto and 0 <= self.pieza_x + x_offset < self.ancho:
                        self.grid[self.pieza_y + y_offset][self.pieza_x + x_offset] = 1
        self.pieza_actual = None
        self.tetris_limpiar_lineas()
        self.ejecutar_evento('ON_START')

    def tetris_verificar_colision(self, x, y, rotacion):
        if not self.pieza_actual: return False
        matriz_pieza = self.pieza_actual[rotacion]
        for y_offset, fila in enumerate(matriz_pieza):
            for x_offset, celda in enumerate(fila):
                if celda == 1:
                    nuevo_x, nuevo_y = x + x_offset, y + y_offset
                    if not (0 <= nuevo_x < self.ancho and 0 <= nuevo_y < self.alto and self.grid[nuevo_y][nuevo_x] == 0):
                        return True
        return False

    def tetris_limpiar_lineas(self):
        nuevo_grid = [fila for fila in self.grid if not all(fila)]
        lineas_limpias = self.alto - len(nuevo_grid)
        if lineas_limpias > 0:
            self.grid = [[0] * self.ancho for _ in range(lineas_limpias)] + nuevo_grid
            for _ in range(lineas_limpias): self.ejecutar_evento('ON_LINE_CLEAR')

    # ------------------------------------------------------------------
    # SNAKE
    # ------------------------------------------------------------------

    def snake_spawn_jugador(self, accion):
        coords = accion['params'][0] if accion['params'] else [self.ancho // 2, self.alto // 2]
        self.serpiente_cuerpo = [(coords[0], coords[1])]
        self.serpiente_direccion = (1, 0)

    def snake_spawn_comida(self):
        while True:
            x, y = random.randint(0, self.ancho - 1), random.randint(0, self.alto - 1)
            if (x, y) not in self.serpiente_cuerpo:
                self.posicion_comida = (x, y)
                break
        # NUEVO S04-S06: se elige al azar un tipo de fruta entre las definidas
        nombre_fruta = random.choice(list(self.frutas_definidas.keys()))
        self.fruta_actual = dict(self.frutas_definidas[nombre_fruta])
        self.fruta_actual['nombre'] = nombre_fruta

    def snake_mover_jugador(self):
        if not self.serpiente_cuerpo: return
        cabeza_x, cabeza_y = self.serpiente_cuerpo[0]
        dir_x, dir_y = self.serpiente_direccion
        nueva_cabeza = (cabeza_x + dir_x, cabeza_y + dir_y)

        if not (0 <= nueva_cabeza[0] < self.ancho and 0 <= nueva_cabeza[1] < self.alto):
            self.racha_actual = 0  # NUEVO S07: la racha se rompe al chocar
            self.ejecutar_evento('ON_COLLISION_WALL')
            return

        if nueva_cabeza in self.serpiente_cuerpo[:-1]:
            self.racha_actual = 0
            self.ejecutar_evento('ON_COLLISION_SELF')
            return

        self.serpiente_cuerpo.insert(0, nueva_cabeza)

        if nueva_cabeza == self.posicion_comida:
            self._comer_fruta()
            self.ejecutar_evento('ON_EAT_FOOD')
        else:
            self.serpiente_cuerpo.pop()

    def _comer_fruta(self):
        """NUEVO: aplica S03 (contador), S04-S06 (puntaje/efecto) y S07 (racha)."""
        fruta = self.fruta_actual or {'nombre': 'DEFAULT', 'score': 1, 'effect': 'NONE'}
        nombre = fruta.get('nombre', 'DEFAULT')

        # S03: contador de tipos de fruta consumida
        self.contador_frutas[nombre] = self.contador_frutas.get(nombre, 0) + 1

        # S07: racha. Cada fruta comida sin chocar aumenta la racha.
        self.racha_actual += 1
        multiplicador = 1.0
        if self.streak_target and self.racha_actual % self.streak_target == 0:
            multiplicador = 1.5  # bono de puntos al alcanzar el objetivo de racha
            self.ejecutar_evento('ON_STREAK_UPDATE')

        puntos = int(fruta.get('score', 1) * multiplicador)
        self.puntuacion += puntos

        # S06: efectos especiales segun el tipo de fruta
        efecto = fruta.get('effect', 'NONE')
        if efecto == 'DOUBLE_POINTS':
            self.puntuacion += puntos
        elif efecto == 'SPEED_BOOST':
            self._activar_efecto_temporal('SPEED_BOOST', velocidad=self.velocidad_base * 0.6, duracion_ticks=40)
        elif efecto == 'SLOW_TIME':
            self._activar_efecto_temporal('SLOW_TIME', velocidad=self.velocidad_base * 1.6, duracion_ticks=40)

        # S10: pista de audio al comer (si el .brick no define PLAY_SOUND en
        # ON_EAT_FOOD, este sonido por defecto sirve como retroalimentacion
        # inmediata; se puede sobreescribir agregando la accion en el .brick)
        self.reproducir_sonido('eat.wav')

    def _activar_efecto_temporal(self, nombre, velocidad, duracion_ticks):
        self.efecto_activo = nombre
        self.efecto_ticks_restantes = duracion_ticks
        self.velocidad_gravedad = velocidad

    def _actualizar_efecto_temporal(self):
        if self.efecto_activo:
            self.efecto_ticks_restantes -= 1
            if self.efecto_ticks_restantes <= 0:
                self.efecto_activo = None
                self.velocidad_gravedad = self.velocidad_base

    def snake_cambiar_direccion(self, direccion):
        if direccion == 'UP' and self.serpiente_direccion[1] != 1:
            self.serpiente_direccion = (0, -1)
        elif direccion == 'DOWN' and self.serpiente_direccion[1] != -1:
            self.serpiente_direccion = (0, 1)
        elif direccion == 'LEFT' and self.serpiente_direccion[0] != 1:
            self.serpiente_direccion = (-1, 0)
        elif direccion == 'RIGHT' and self.serpiente_direccion[0] != -1:
            self.serpiente_direccion = (1, 0)

    def snake_crecer(self):
        pass

    # ------------------------------------------------------------------
    # ACCESIBILIDAD: PAUSA / SILENCIO / AUDIO (S08, S09, S10)
    # ------------------------------------------------------------------

    def snake_toggle_pausa(self):
        self.pausado = not self.pausado

    def snake_toggle_mute(self):
        self.silenciado = not self.silenciado

    def reproducir_sonido(self, nombre_archivo):
        """S10: reproduce una pista de audio corta, respetando el silencio (S08)."""
        if self.silenciado:
            return
        if AUDIO_DISPONIBLE:
            try:
                winsound.PlaySound(nombre_archivo, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                # Si el archivo no existe o falla el driver de audio, el
                # juego no debe interrumpirse por esto.
                pass

    # ------------------------------------------------------------------
    # SALIDA
    # ------------------------------------------------------------------

    def mostrar_game_over(self):
        messagebox.showinfo("Juego Terminado", "Puntuacion Final: " + str(self.puntuacion))
        self.root.destroy()
        sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 runtime.py <archivo_juego.json>")
        sys.exit(1)
    archivo_juego = sys.argv[1]
    try:
        with open(archivo_juego, 'r') as f:
            datos_juego = json.load(f)
    except IOError:
        print("Error: No se pudo encontrar el archivo " + archivo_juego)
        sys.exit(1)
    juego = Juego(datos_juego)
    juego.run()