# Resumen Ejecutivo  
Se propone un pipeline de reconocimiento de personajes y lugares en textos literarios en español usando herramientas NLP clásicas (spaCy, Stanza, Flair, etc.) combinado con reglas específicas. Se entrenan/cargan modelos NER en español (por ejemplo, spaCy `es_core_news_sm`, Stanford Stanza y Flair) optimizados para alta precisión en nombres propios completos, títulos, apellidos y variantes. Tras el etiquetado NER se aplican reglas post-procesamiento (regex, diccionarios de nombres y toponimia) para normalizar menciones (p. ej. unir “Sr. García” con “García”), y técnicas simples de correferencia para agrupar pronombres y epítetos con sus personajes. El pipeline único en Python procesará ~90 *chunks* (bloques de texto) en unos minutos (usando batching y GPU si es posible). Se recomienda evaluar con métricas de entidad (precisión, recall, F1) sobre conjuntos de referencia en español (CoNLL-2002, AnCora, WikiNER) y probarlo con casos difíciles (p. ej. nombres sueltos, epítetos). A continuación se compara brevemente cada modelo, se propone la arquitectura de pipeline y se dan pautas de implementación y evaluación.

## Herramientas NER en español  
Los modelos NER disponibles en español muestran rangos de precisión similares, alrededor de 88–91 % F1. Por ejemplo, el modelo pequeño de spaCy (`es_core_news_sm`) reporta F1≈0.89. El modelo de Stanford Stanza para español alcanza F1≈0.886 (sobre AnCora). Flair ofrece un modelo “ner-spanish-large” (basado en XLM-RoBERTa) con F1≈0.905. Un modelo BERT multilingüe fine-tuneado (BETO) ha mostrado ~90.2 % F1. En general: spaCy y Stanza son más livianos y muy rápidos (spaCy puede procesar ≳10 000 palabras/s en CPU), mientras que Flair/Transformers brindan algo más de precisión a costa de mayor costo computacional. Todos clasifican etiquetas como PER (personas) y LOC (lugares) que cubren personajes y topónimos mínimos requeridos. Además existen herramientas basadas en reglas o gazetteers (diccionarios de nombres y lugares), útiles para detectar casos específicos y filtrar falsos positivos.

| **Herramienta/Modelo**             | **Precisión NER (F1 en español)** | **Requisitos HW**         | **Velocidad**                | **Integración**                         |
|-----------------------------------|-------------------------------|--------------------------|-----------------------------|-----------------------------------------|
| **spaCy (es_core_news_sm)**       | ~0.89          | CPU moderado (sm)        | Muy rápida (≈10 000 palabras/s) | Muy fácil (instalación pip)             |
| **spaCy (es_core_news_md/lg)**    | ~0.89–0.90 (md, lg)           | Similar (+vocab grande)  | Rápida (lg algo más lenta)  | Fácil (pip)                             |
| **Stanford Stanza (es)**          | 0.886 (AnCora)  | CPU o GPU opcional       | Rápida (≈878 wds/s CPU)     | Fácil (pip)                             |
| **Flair (spanish-large)**         | 0.905 (CoNLL-03)| GPU recomendado, 8+ GB   | Lenta en CPU (~323 wds/s, mejora en GPU) | Moderada (pip, depende de PyTorch)     |
| **Transformers BETO NER**         | 0.902 (Conll2002)| GPU casi obligado       | Lenta en CPU (similar a Flair) | Moderada (HF + PyTorch)                  |
| **Reglas/Gazetteers**             | Variable (depende de cobertura) | Mínimos                 | Muy rápido (diccionarios locales) | Manual (código, listas externas)       |

Los modelos basados en aprendizaje (ML) distinguen categorías PER y LOC estándar. Para evitar falsos positivos, conviene filtrar entidades genéricas (p.ej. ``MISC`` ambiguas) y apoyarse en diccionarios de nombres (nombres de pila y apellidos frecuentes en español) y de topónimos (países, ciudades, regiones, incluso datos de GeoNames). La tabla compara precisión reportada, requisitos de hardware, latencia y facilidad de uso de cada opción. En general, spaCy/Stanza ofrecen gran velocidad con precisión aceptable; Flair/Transformers mejoran un poco F1 sacrificando tiempo. En un script único se puede combinar uno o varios, aunque a menudo basta con un modelo NER robusto (p.ej. Stanza o spaCy-md) y reforzar mediante reglas ad-hoc.

## Resolución de correferencias  
Para agrupar variantes de nombres (pronombres, epítetos, títulos), es necesario resolver coreferencias. En español **no hay** un modelo libre de coref tan maduro como en inglés. Herramientas como **NeuralCoref** (spaCy) o AllenNLP e2e sólo soportan inglés. Stanford CoreNLP ofrece coref de regla/ML genérico, pero no es trivial de integrar en Python sin Java. Tampoco hay modelos Transformers pre-entrenados públicos de coref en español. Por ello se recomiendan estrategias heurísticas:

- **Normalización de nombres**: Unificar títulos y apellidos. Por ejemplo, si NER detecta “Samsa” PER y antes aparece “Sr.” o “Señor”, fusionar como “Sr. Samsa”. Regex simples (`r"\b(Sr\.?|Señor|Sra\.?|Señora|Dr\.?|Doña)\s+(\w+)"`) pueden capturar honoríficos precedentes. Lo mismo para “Don X”, “la Reina Isabel” (conservar “Reina Isabel” como PER).
- **Coincidencia ortográfica**: Agrupar menciones con apellidos idénticos (p.ej. “Martínez” y “Pedro Martínez”) y variantes de nombre (con nombre completo vs solo apellido). Mantener un diccionario de personajes hallados para referir casos posteriores.
- **Pronombres**: Resolver “él/ella” al antecedente más próximo de la misma persona dentro del chunk (utilizando género/numero y parseo sintáctico ligero). Por ejemplo, si aparece “La abuela se sentó. **Ella** contó historias”, enlazar “Ella” con “la abuela”.
- **Epítetos y roles**: Tratar “el doctor”, “mi hermano”, “nuestro guía” como referidos al personaje anterior más cercano o conocido. Esto es muy dependiente del contexto literario y puede no automatizarse totalmente, pero reglas simples (p.ej. “el [sustantivo común] + PER precedente”) ayudan en algunos casos.

En la práctica, tras extraer con NER se formarán clusters heurísticos: por string exacta o compartida (apellido/nombre), o via pronombres genéricos. No hay citas específicas para estas técnicas, pues son convenciones implementadas por investigadores NLP (véase [36†L703-L711] en investigaciones de co-referencia multilingüe y adaptaciones). En resumen, usar agrupamiento por nombre-apellido y priorizar enlace de pronombres a menciones cercanas suele cubrir la mayoría de variantes de personaje en un chunk.

## Pipeline propuesto  

```mermaid
graph LR
  Texto[Texto (chunk)] --> Toks[Tokenización y segmentación]
  Toks --> NER{Modelo NER}
  NER -->|PER/LOC| Post[Post-procesamiento]
  Post --> Reglas[Reglas y Normalización]
  Reglas --> Coref[Resolución de correferencias]
  Coref --> Salida[Salida: personajes & lugares únicos por chunk]
```

1. **Tokenización y segmentación**: Dividir el *chunk* en oraciones y tokens (spaCy/Stanza).
2. **Etiquetado NER**: Aplicar modelo entrenado (spaCy/Stanza/Flair) sobre cada chunk. Filtrar solo entidades *PER* y *LOC* (personas y lugares).
3. **Post-procesamiento**:  
   - **Unión de variantes**: Si el NER etiquetó “García” y antes estaba “Sr.”, crear la entidad “Sr. García”.  
   - **Diccionarios**: Verificar si la entidad coincide o contiene nombres de pila o lugares conocidos (para descartar falsos positivos como palabras comunes).  
4. **Corrección de toponimia compuesta**: Garantizar capturar lugares multi-palabra (“Ciudad de México”, “Sierra de Guadarrama”). Si el modelo los divide, reensamblar frases adyacentes con mayúsculas o conjunciones.  
5. **Correferencia**: Agrupar menciones al mismo personaje dentro del chunk (pronombres, epítetos) usando heurísticas (véase sección anterior). Esto produce entidades canónicas (p.ej. “Gregorio Samsa” agrupa también “Gregorio”, “Samsa”, “Sr. Samsa”).
6. **Salida**: Para cada chunk, devolver la lista de personajes y lugares únicos encontrados (con la mención “mínima” canónica, idealmente nombre completo).

Este diagrama ilustra el flujo. El pipeline completo puede implementarse en un único script Python, cargando una sola vez cada modelo. Se pueden procesar los 90 chunks secuencialmente o por lotes (batch) con `nlp.pipe` (spaCy) o en paralelo. Las dimensiones de entrada (chunks cortos de obra literaria) son manejables, por lo que no se esperan cuellos de botella más allá del NER y la correferencia.

## Implementación y optimización  
- **Dependencias principales**: spaCy (3.x) con el modelo `es_core_news_sm` o `md`; [Stanza](https://stanfordnlp.github.io/stanza/) (Pipeline `lang='es', processors='tokenize,ner'`); [Flair](https://flairNLP.github.io/) (SequenceTagger carga `flair/ner-spanish-large`); [Transformers](https://huggingface.co/) para modelos tipo BETO (`mrm8488/bert-spanish-cased-finetuned-ner`); paquetes auxiliares (`regex`, `pandas`, etc.).  
- **Carga y recursos**: Instalar modelos previamente (`spacy download`, `stanza.download('es')`, `Tagger.load(...)`). Si hay GPU disponible, usarla con Flair/Transformers para acelerar (Flair automáticamente usa GPU si la detecta; en HuggingFace con `torch.device("cuda")`).  
- **Desactivar componentes innecesarios**: En spaCy, cargar solo NER (`disable=['parser','tagger','lemmatizer']`) para ahorrar tiempo, si no se usan. Para Stanza, pedir solo NER.  
- **Batching**: Procesar texto en lotes (ej. `for doc in nlp.pipe(chunks, batch_size=50, n_process=4)` en spaCy v3) maximiza throughput. Lo mismo en Transformers: la pipeline de HF acepta listas de strings.  
- **Caching**: Mantener en memoria diccionarios de personajes y lugares detectados para evitar recomputar reglas complejas. Por ejemplo, almacenar cada nombre propio hallado y sus variantes para facilitar la correferencia.  
- **Reglas regex**: A modo de “fallback”, después del etiquetado se pueden aplicar expresiones regulares que capturen patrones comunes no detectados por el modelo (p.ej. `r"\b(Señor[ea]?|Sr\.|Sra\.)\s+[A-Z][a-z]+"` para honoríficos, o `r"\b[A-Z]\w+\s+de\s+[A-Z]\w+"` para lugares compuestos). Estas reglas mejoran recall en casos específicos.  
- **Ejemplo de código**:
  ```python
  import spacy, stanza
  from flair.models import SequenceTagger
  
  # Inicializar modelos (ejecutar una vez)
  nlp_spacy = spacy.load("es_core_news_md", disable=["parser","tagger"])
  stanza.download("es")  # solo la primera vez
  nlp_stanza = stanza.Pipeline(lang="es", processors="tokenize,ner", use_gpu=False)
  flair_tagger = SequenceTagger.load("flair/ner-spanish-large")

  def extract_entities(chunk_text):
      doc = nlp_spacy(chunk_text)
      ents = [(ent.text, ent.label_) for ent in doc.ents if ent.label_ in ("PER","LOC")]
      # Opcional: usar Stanza o Flair para complementar:
      # doc_stanza = nlp_stanza(chunk_text)
      # ents += [(ent.text, ent.type) for sent in doc_stanza.sentences for ent in sent.ents]
      # (Tras esto, unir listas y eliminar duplicados similarmente)
      # Aplicar reglas de post-procesamiento:
      # p.ej. regex honoríficos, fusión de fragmentos, etc.
      # Correferencia básica:
      # p.ej. identificar pronombres "él/ella" y reasignarles la última PER válida.
      return ents

  # Ejecución en lote
  results = []
  for chunk in texto_chunks:
      entities = extract_entities(chunk)
      results.append(entities)
  ```
  En este pseudocódigo se muestra cómo cargar modelos y procesar *chunks*. Nótese el uso de `disable` para acelerar spaCy. Se pueden paralelizar los bucles (`nlp.pipe`) y aprovechar GPU en Flair/HF para mayor velocidad.

## Evaluación (métricas y datos)  
Se recomienda medir **precisión, recall y F1** a nivel de entidad reconocida (no a nivel de token) usando scripts CoNLL estándar (como `conlleval` o la clase `Scorer` de spaCy). Para NER en español existen conjuntos de referencia públicos: el dataset **CoNLL-2002 (Spanish)** y el corpus **AnCora** brindan anotaciones de PER y LOC. También se dispone de **WikiNER** (etiquetado automático de Wikipedia). En investigaciones se reporta que los modelos actuales obtienen ~88–90 % F1 en español (por ejemplo spaCy: 0.891; Stanza: 0.886; Flair: 0.905; BERT es-BETO: 0.902). Además, los datos específicos de obras literarias pueden no coincidir al 100 % con newswire, por lo que es útil crear un *set* pequeño anotado manualmente a modo de validación.

**Métricas sugeridas**: precisión, recall y F1 a nivel de mención (evaluando entidad completa). Para la correferencia, se pueden usar métricas clásicas (MUC, B<sup>3</sup>, CEAF) pero dada la complejidad basta evaluar manualmente la unión de variantes. 

**Datasets de referencia**:
- *CoNLL-2002 (español)*: ~30K entidades anotadas (Personas, Organizaciones, Locaciones) en textos periodísticos.  
- *AnCora-Entidades*: corpus académico hispánico anotado por el proyecto AnCora (C-Entidades). Se ha usado para Stanza (F1=88.6).  
- *WikiNER (español)*: etiquetado automático de Wikipedia para NER, útil para entrenamiento/validación adicional.  

**Resultados esperados**: Se esperaría obtener F1 en el rango 0.85–0.90 con modelos pre-entrenados, mejorando con reglas/herramientas adicionales. 

## Plan de pruebas y casos difíciles  
Para validar y ajustar el sistema, se propone:

- **Corpus de prueba personalizado**: recolectar ~20–30 *chunks* de una obra literaria (o varias) y anotarlos manualmente (personajes y lugares). Comparar con la salida automática para medir P/R/F1.  
- **Métricas**: utilizar un script de evaluación de NER (p.ej. [seqeval](https://github.com/chakki-works/seqeval) o spaCy Scorer) para obtener P/R/F1 de los resultados frente al gold standard.  

**Casos de prueba complicados** (ejemplos de “hard cases” a cubrir):  

- *Formas variables de un personaje*:  
  - *Honoríficos y títulos*: “**Sr. Gómez** llegó tarde” (debe extraer “Sr. Gómez”), “**Don Quijote de la Mancha** cabalga con *Sancho Panza*” (extraer “Don Quijote” y “Sancho Panza”).  
  - *Epítetos*: “**El Capitán Torres** ordenó…” o “**La Reina Isabel** desfiló”. El modelo debe capturar el nombre completo (con rango si existe) o al menos el nombre propio (“Capitán Torres”, “Reina Isabel”).  
  - *Menciones parciales*: “Juan habló con **María**. **Ella** sonrió.” Debe asociar “Ella” a María en correferencia.  
  - *Solo apellido*: “**García** nunca volvió”, cuando previamente se mencionó “Pedro García”. El sistema debe reconocer “García” como el mismo personaje o pedir la mención completa.  
- *Topónimos compuestos*: “**Ciudad de Buenos Aires** es grande”, “Montañas Rocosas”. Asegurarse de no dividir en entidades separadas (“Ciudad”, “Buenos Aires” unidas).  
- *Topónimos geográficos vs. comunes*: “El **Río Amazonas** es largo” (extraer “Río Amazonas”), pero no etiquetar “rio” por separado.  
- *Ambigüedad: nombres y sustantivos comunes*: “**Florencia** es hermosa” (¿ciudad o persona? contexto literario define). El NER puede etiquetar “Florencia” como PER o LOC según. Control manual en pruebas.  
- *Pronombres y posesivos*: “Carlos saludó a **María**. *Su* hermano lo vio.” Debe extraer “Carlos”, “María”, y asociar “su hermano” a María (correferencia).  
- *Nombres sin contexto*: “**Lázaro** caminó solo.” (Lázaro nombre propio, difícil si no hay contexto).  
- *Nombres extranjeros o inusuales*: “**Nabokov** visitó Madrid” (apellido ruso, no muy frecuente).  
- *Posibles falsos positivos*: “*Casa* Blanca es un edificio” (debe etiquetar “Casa Blanca” como LOC), pero no marcar “blanca” aislado ni palabras comunes (“hueso Santiago”, “Elcano”).

Se probarán al menos 10–15 de estos casos, verificando que el pipeline los maneje correctamente. Cada caso debe ir con entrada de texto y el resultado esperado de personajes/lugares extraídos. Esto permitirá ajustar reglas regex o filtrar entidades erróneas.

```markdown
*Ejemplo de casos de prueba*:

- “El **Sr. García** y **María** fueron a **Londres**.” → PERSON: Sr. García; María | LOC: Londres.  
- “**Don Quijote de la Mancha** luchó contra **sancho Panza**.” → PERSON: Don Quijote; Sancho Panza.  
- “**Gregorio** le dijo a **Samsa** que él volverá.” → PERSON: Gregorio; Samsa (agrupados si son el mismo).  
- “El **Monte Everest** es la montaña más alta.” → LOC: Monte Everest.  
- “**Barcelona** y **Madrid** se disputan el campeonato.” → LOC: Barcelona; Madrid.  
- “**Señora de Braganza** saludó a los nobles.” → PERSON: Señora de Braganza.  
- “Mi hermano **Antonio** vive en **Colombia**.” (prueba conjunción home/place).  
- “La **Reina Isabel** asistió al evento. **Ella** ofreció un discurso.” → PERSON: Reina Isabel (agrupa “Ella”).  
```

Este plan de pruebas, junto con métricas claras, ayudará a asegurar la fiabilidad del sistema y a identificar dónde refinar reglas o ajustes de modelo. 

