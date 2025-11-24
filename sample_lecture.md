MACHINE LEARNING LECTURE 1: NEURAL NETWORKS
==========================================

[Page 1: Introduction]

Welcome to Machine Learning! In this lecture, we'll cover the fundamentals of neural networks, one of the most powerful tools in modern AI.

Topics:
1. What is a Neural Network?
2. Architecture and Components
3. Training Process
4. Applications

[Page 2: What is a Neural Network?]

A neural network is a computational model inspired by biological neural networks in the brain. It consists of interconnected nodes (neurons) organized in layers.

Key Components:
- Input Layer: Receives raw data
- Hidden Layers: Process information through weighted connections
- Output Layer: Produces final predictions
- Activation Functions: Introduce non-linearity

[Page 3: Architecture]

Neural Network Architecture:

Input Layer → Hidden Layer 1 → Hidden Layer 2 → Output Layer

Each connection has a weight (w) that determines its strength.
Each neuron applies an activation function to its inputs.

Common activation functions:
- Sigmoid: σ(x) = 1/(1+e^(-x))
- ReLU: f(x) = max(0, x)
- Tanh: tanh(x) = (e^x - e^(-x))/(e^x + e^(-x))

[Page 4: Forward Propagation]

Forward propagation is the process of passing input through the network:

1. Input data enters the input layer
2. Each neuron computes: output = activation(Σ(weight × input) + bias)
3. Outputs become inputs for next layer
4. Process repeats until output layer

Example:
If input x=2, weight w=0.5, bias b=1, activation=ReLU:
output = ReLU(0.5 × 2 + 1) = ReLU(2) = 2

[Page 5: Training - Loss Functions]

Training involves adjusting weights to minimize prediction error.

Loss Functions measure how wrong predictions are:

- Mean Squared Error (MSE): L = (1/n)Σ(y_true - y_pred)²
  Used for regression problems

- Cross-Entropy: L = -Σ(y_true × log(y_pred))
  Used for classification problems

The goal is to minimize loss by finding optimal weights.

[Page 6: Gradient Descent]

Gradient Descent is an optimization algorithm that minimizes the loss function.

Process:
1. Calculate gradient (derivative) of loss with respect to each weight
2. Update weights in opposite direction of gradient
3. Repeat until convergence

Update rule: w_new = w_old - α × ∂L/∂w

Where α is the learning rate (typically 0.001 to 0.1)

Learning Rate:
- Too high → overshooting, instability
- Too low → slow convergence
- Just right → efficient optimization

[Page 7: Backpropagation]

Backpropagation computes gradients efficiently using the chain rule.

Algorithm:
1. Forward pass: compute predictions
2. Calculate loss at output layer
3. Backward pass: propagate error backwards through layers
4. Compute gradient for each weight using chain rule
5. Update weights using gradient descent

Chain Rule Example:
∂L/∂w₁ = ∂L/∂output × ∂output/∂activation × ∂activation/∂w₁

[Page 8: Training Process Summary]

Complete Training Loop:

1. Initialize weights randomly
2. For each epoch:
   a. Forward propagation (make predictions)
   b. Calculate loss
   c. Backpropagation (compute gradients)
   d. Update weights (gradient descent)
3. Repeat until loss converges or max epochs reached

Hyperparameters to tune:
- Learning rate
- Batch size
- Number of epochs
- Number of hidden layers
- Neurons per layer

[Page 9: Overfitting and Regularization]

Overfitting occurs when a model learns training data too well, including noise, leading to poor generalization on new data.

Signs of Overfitting:
- Low training loss, high test loss
- Large gap between training and validation accuracy
- Model performs well on seen data, poorly on unseen data

Prevention Techniques:

1. Regularization
   - L1 (Lasso): Σ|w|
   - L2 (Ridge): Σw²
   
2. Dropout: Randomly deactivate neurons during training

3. Early Stopping: Stop training when validation loss stops improving

4. More Training Data: Helps model generalize better

5. Data Augmentation: Create variations of training data

[Page 10: Practical Applications]

Neural Networks are used in:

1. Computer Vision
   - Image classification
   - Object detection
   - Facial recognition
   
2. Natural Language Processing
   - Machine translation
   - Sentiment analysis
   - Text generation

3. Speech Recognition
   - Voice assistants
   - Transcription services

4. Recommendation Systems
   - Netflix, Spotify recommendations
   - E-commerce suggestions

5. Game Playing
   - AlphaGo
   - Chess engines

[Page 11: Summary]

Key Takeaways:

1. Neural networks consist of layers of interconnected neurons
2. Forward propagation passes data through the network
3. Loss functions measure prediction error
4. Gradient descent optimizes weights to minimize loss
5. Backpropagation efficiently computes gradients
6. Regularization prevents overfitting
7. Neural networks power modern AI applications

Next Lecture: Deep Learning and Convolutional Neural Networks

[Page 12: Quiz Questions]

Test your knowledge:

1. What are the three main types of layers in a neural network?
2. What is the purpose of an activation function?
3. How does gradient descent update weights?
4. What is backpropagation and why is it important?
5. Name three techniques to prevent overfitting.
6. What is the difference between L1 and L2 regularization?
7. What does the learning rate control in gradient descent?