"""Inject BANDERA questions by sequential position within each book.

Reads questions from add_questions_to_banderas.py grouped by book_id (in order),
then assigns question[i] to the i-th BANDERA in each reader JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
READER_DIR = ROOT / "data" / "outputs" / "readers"
RETRIEVAL_DIR = ROOT / "data" / "outputs" / "retrieval"

# ── Questions in order per book ──────────────────────────────────────
# Extracted from add_questions_to_banderas.py + manual Kafka questions
QUESTIONS_BY_BOOK: dict[str, list[str]] = {
    "la_metamorfosis_franz_kafka": [
        "¿Por qué Gregorio, al despertar convertido en insecto, se preocupa más "
        "por llegar tarde al trabajo que por su nueva apariencia física? "
        "¿Qué dice esto sobre su vida antes de la transformación?",
        "¿Por qué Gregorio se niega a abrir la puerta cuando su familia y el "
        "apoderado se lo piden? ¿Qué teme que pase si lo ven?",
        "¿Cómo defiende la madre a Gregorio frente a las acusaciones del "
        "apoderado? ¿Qué revelan sus palabras sobre la relación familiar?",
        "Cuando Gregorio por fin abre la puerta y todos lo ven, ¿cómo "
        "reacciona cada miembro de la familia? ¿Qué reacción te parece "
        "más impactante y por qué?",
        "¿Por qué el padre reacciona con tanta violencia al ver a Gregorio "
        "fuera de su habitación? ¿Qué sentimientos crees que motivan que "
        "lo ataque con el bastón y el periódico?",
        "Al inicio del capítulo 2, ¿cómo cambian los gustos alimenticios "
        "de Gregorio? ¿Qué crees que simboliza el hecho de que ya no le "
        "guste la leche, su bebida favorita?",
        "¿Qué descubre Gregorio sobre la situación económica familiar que "
        "no sabía antes? ¿Cómo cambia esto la imagen que tenía de sí mismo "
        "como proveedor del hogar?",
        "La hermana y la madre discuten sobre vaciar la habitación. ¿Qué "
        "representa para cada una la decisión de quitar los muebles? "
        "¿Quién crees que tiene razón?",
        "¿Por qué Gregorio se aferra al cuadro de la mujer envuelta en "
        "pieles? ¿Qué crees que simboliza ese objeto para él en medio "
        "del vaciamiento de su habitación?",
        "¿Cómo ha cambiado el padre físicamente y en su actitud desde que "
        "Gregorio dejó de trabajar? ¿Qué crees que significa el uniforme "
        "de ordenanza que ahora usa?",
        "Al inicio del capítulo 3, ¿cómo ha cambiado la vida de cada "
        "miembro de la familia? ¿Quién ha experimentado la transformación "
        "más notable?",
        "¿Cómo reflejan la habitación de Gregorio —ahora llena de trastos "
        "y suciedad— y el trato de la asistenta el deterioro de su "
        "relación con la familia?",
        "Cuando Greta dice «tenemos que intentar quitárnoslo de encima», "
        "¿qué argumentos da? ¿Crees que la familia tomó la decisión "
        "correcta al abandonar a Gregorio?",
    ],
    "el_maravilloso_mago_de_oz_baum_lyman_frank": [
        "¿Cómo es la vida de Dorothy en Kansas antes del ciclón? ¿Por qué crees que sueña con un lugar colorido y diferente?",
        "Dorothy conoce al Espantapájaros. ¿Qué desea este personaje y por qué? ¿Crees que ya posee lo que busca sin saberlo?",
        "Dorothy y el Espantapájaros encuentran al Leñador de Hojalata. ¿Qué simboliza su deseo de tener un corazón? ¿Qué cualidades demuestra que ya lo tiene?",
        "Aparece el León Cobarde. ¿Por qué se considera cobarde y qué actos de valentía realiza sin darse cuenta? ¿Qué crees que representa este personaje?",
        "El grupo cruza el campo de amapolas. ¿Qué peligro enfrentan y cómo se ayudan entre sí? ¿Qué demuestra esto sobre su amistad?",
        "En su viaje conocen a la Reina de los Ratones. ¿Cómo demuestra el grupo el valor de la solidaridad ayudando a seres más pequeños?",
        "Llegan a la Ciudad Esmeralda y conocen al Mago de Oz. ¿Qué impresión les causa? ¿Por qué crees que cada uno debe usar gafas verdes?",
        "El Mago les ordena matar a la Bruja Maligna de Occidente. ¿Qué revela esta misión sobre el verdadero carácter del Mago?",
        "Tras derrotar a la bruja, el grupo descubre que el Mago es un hombre común. ¿Cuál es la gran lección que aprenden Dorothy y sus amigos? ¿Qué significan realmente el cerebro, el corazón y el valor?",
    ],
    "el_viejo_y_el_mar_ernest_hemingway": [
        "¿Cómo se describe al viejo Santiago al inicio de la historia? ¿Qué significado crees que tiene que lleve 84 días sin pescar?",
        "¿Cómo es la relación entre Santiago y Manolín? ¿Por qué los padres del muchacho lo obligaron a cambiar de bote?",
        "Santiago y Manolín hablan de béisbol y de los grandes jugadores. ¿Por qué Hemingway incluye estas conversaciones? ¿Qué simboliza el béisbol para ellos?",
        "El viejo y el muchacho fingen que tienen comida y una atarraya. ¿Por qué mantienen esta ficción? ¿Qué dice sobre su orgullo y su amistad?",
        "Santiago se prepara para salir solo al mar. ¿Qué sentimientos experimenta? ¿Por qué decide ir más lejos que los demás pescadores?",
        "El viejo despierta a Manolín antes del amanecer. ¿Qué significa para Santiago la compañía del muchacho, aunque sea solo al inicio de la jornada?",
        "Santiago rema mar adentro y reflexiona sobre el mar, los peces voladores y las aves. ¿Qué relación tiene con la naturaleza? ¿La ve como amiga o enemiga?",
        "El viejo lanza sus sedales con precisión. ¿Cómo demuestra su experiencia y conocimiento del mar en esta escena?",
        "Mientras espera, Santiago reflexiona sobre su soledad. ¿Qué piensa del mar y de su lugar en él? ¿Está realmente solo?",
        "El gran pez muerde el anzuelo. ¿Cómo reacciona Santiago? ¿Por qué habla con el pez como si fuera un igual?",
        "Santiago recuerda cuando él y Manolín pescaron una pareja de agujas y cómo lloraron por la hembra. ¿Qué revela esto sobre su sensibilidad?",
        "La batalla con el pez continúa. Santiago sufre calambres y dolor. ¿Cómo soporta el sufrimiento físico? ¿Qué frases se repite a sí mismo?",
        "El viejo come el bonito crudo para mantenerse fuerte. ¿Qué demuestra esto sobre su voluntad de sobrevivir? ¿Por qué se disculpa con el pez que mató para comer?",
        "Santiago por fin ve el pez cuando salta fuera del agua. ¿Cómo describe su tamaño y belleza? ¿Por qué siente admiración por su adversario?",
        "¿Quién es el verdadero oponente en esta batalla? ¿El pez, el mar, el propio cuerpo de Santiago o algo más? Explica tu respuesta.",
        "Santiago recuerda su juventud en Casablanca y la pulseada que duró un día entero. ¿Qué paralelos hay entre aquella pulseada y la lucha con el pez?",
        "Después de días de lucha, Santiago finalmente arponea al pez. ¿Qué siente en ese momento? ¿Es una victoria o también una pérdida?",
        "Santiago amarra el pez al bote y emprende el regreso. ¿Qué peligros presiente? ¿Por qué dice que el verdadero desafío apenas comienza?",
        "El pez nada haciendo círculos mientras Santiago se prepara para el golpe final. ¿Por qué el viejo siente que debe demostrarle algo al pez?",
        "Llega el primer tiburón (el Mako). ¿Cómo defiende Santiago al pez? ¿Qué pierde además del arpón y cuarenta libras de carne?",
        "Santiago reflexiona sobre si fue un pecado matar al pez. ¿Qué significado tienen estas reflexiones? ¿Qué está cuestionando realmente?",
        "Llegan más tiburones. Santiago ahora lucha con un cuchillo amarrado a un remo. ¿Cómo cambia su actitud de la primera defensa a esta?",
        "El viejo pierde el cuchillo y sigue peleando. ¿Qué armas va improvisando? ¿Por qué sigue luchando si sabe que está perdiendo?",
        "Llegan los galanos (tiburones de puntas blancas) al anochecer. ¿En qué se diferencia su ataque? ¿Qué simbolizan estos tiburones finales?",
        "Santiago golpea a los tiburones con el cabo del timón hasta que no queda nada. ¿Qué representa esta lucha final a pesar de saberla inútil?",
        "Santiago llega a la costa de noche con el esqueleto del pez. ¿Fue derrotado o victorioso? ¿Qué piensan los demás pescadores al ver los restos?",
    ],
    "cronica_de_una_muerte_anunciada_gabriel_garcia_marquez": [
        "¿Quién es Santiago Nasar y qué sabemos de él por el prólogo? ¿Qué anuncio se hace desde el principio sobre su destino?",
        "Santiago Nasar soñó con árboles y llovizna la noche antes de morir. ¿Por qué Plácida Linero, su madre, falló en interpretar esos sueños? ¿Qué ironía encuentras en esto?",
        "¿Quién es Victoria Guzmán y qué relación tuvo con Ibrahim Nasar? ¿Por qué no advirtió a Santiago de lo que iba a pasar?",
        "¿Qué coincidencias fatales rodearon la muerte de Santiago Nasar? ¿Crees que eran simples casualidades o había algo más?",
        "¿Quién es Bayardo San Román y cómo se describe su llegada al pueblo? ¿Qué impresión causa en los demás?",
        "¿Por qué se casó Bayardo San Román con Ángela Vicario? ¿Qué crees que buscaba realmente en ella?",
        "¿Qué precio pagó Bayardo San Román para conseguir a Ángela? ¿Qué dice esto sobre el poder y el amor en el pueblo?",
        "Describe a Ángela Vicario. ¿Por qué crees que su familia la crió como lo hizo? ¿Qué destino le esperaba según las costumbres del pueblo?",
        "¿Cómo fue la boda de Bayardo y Ángela? ¿Qué detalle de la fiesta te parece más significativo sobre los valores de la sociedad del pueblo?",
        "La noche de bodas, Bayardo devuelve a Ángela a su familia. ¿Qué revela esta escena sobre las apariencias y el honor?",
        "Los gemelos Vicario van a matar a Santiago Nasar pero, ¿realmente querían hacerlo? ¿Qué señales dieron para que alguien los detuviera?",
        "¿Por qué nadie en el pueblo detuvo a los gemelos Vicario si todos sabían lo que iba a pasar? ¿Qué responsabilidad crees que tiene cada habitante?",
        "Santiago Nasar disfrutaba disfrazar a las mujeres del pueblo. ¿Qué nos dice esto sobre su personalidad? ¿Cómo contrasta con la imagen que los gemelos tienen de él?",
        "Cuando el coronel Lázaro Aponte le quita los cuchillos a los gemelos, ¿por qué estos consiguen otros? ¿Qué responsabilidad tiene la autoridad en lo que ocurre?",
        "Los gemelos Vicario son encarcelados pero, ¿cómo se sienten en prisión? ¿Crees que su castigo fue justo?",
        "Ángela Vicario empieza a escribirle cartas a Bayardo San Román años después. ¿Por qué crees que lo hace? ¿Qué dice esto sobre su transformación como personaje?",
        "¿Por qué el juez instructor estaba tan obsesionado con el caso? ¿Qué dice el narrador sobre el sumario y las notas marginales del juez?",
        "Momentos antes de morir, Santiago Nasar habla en árabe con Yamil Shaium. ¿Qué significado tiene este detalle cultural en la historia?",
        "Cristo Bedoya busca desesperadamente a Santiago para advertirle. ¿Por qué falla en encontrarlo? ¿Qué papel juega el azar en esta historia?",
        "Describe la escena final de la muerte de Santiago Nasar. ¿Por qué crees que García Márquez eligió narrar así el desenlace? ¿Qué sentimientos te provoca?",
    ],
}


def inject() -> None:
    for rp in sorted(READER_DIR.glob("*.reader.json")):
        data = json.loads(rp.read_text(encoding="utf-8"))
        book_id = data["book_id"]

        if book_id not in QUESTIONS_BY_BOOK:
            continue

        qs = QUESTIONS_BY_BOOK[book_id]
        banderas = [b for b in data["blocks"] if b["type"] == "BANDERA"]

        for i, bandera in enumerate(banderas):
            if i < len(qs):
                bandera["questions"] = [qs[i]]
            else:
                bandera["questions"] = None

        with open(rp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

        with_q = sum(1 for b in banderas if b.get("questions") and len(b["questions"]) > 0)
        print(f"  {rp.name}: {with_q}/{len(banderas)}")


if __name__ == "__main__":
    inject()
